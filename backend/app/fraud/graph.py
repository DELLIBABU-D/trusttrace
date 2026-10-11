"""Fraud relationship graph (NetworkX).

Nodes: candidate accounts and linking signals (verified mobile number, strong face match, browser, network).
Edges join a candidate to a signal it has. Two accounts are "linked" when they share a signal node.

Strength:  strong = same OTP-verified mobile number, or face similarity >= the duplicate threshold
           medium = same browser ID (keyed hash)
           weak   = same network address (keyed hash) - shown for context only
A connected cluster is NOT a confirmed fraud ring: it only shows which accounts share something and needs review.
Other accounts are masked unless they applied to the viewing recruiter's organisation.
"""
from __future__ import annotations

import hashlib

import networkx as nx
from sqlalchemy.orm import Session

from ..models import Application, Candidate, DeviceSighting, DuplicateAlert, Job, User
from .patterns import mask

STRENGTH_ORDER = {"strong": 3, "medium": 2, "weak": 1}


def _phone_key(phone: str) -> str:
    digits = "".join(ch for ch in phone or "" if ch.isdigit())[-10:]
    return hashlib.sha256(f"phone:{digits}".encode()).hexdigest()[:12] if len(digits) == 10 else ""


def build(db: Session, include_weak: bool = True) -> nx.Graph:
    g = nx.Graph()
    cands = db.query(Candidate).join(User, Candidate.user_id == User.id).all()
    for c in cands:
        g.add_node(f"cand:{c.id}", kind="candidate", candidate_id=c.id)
        if c.phone_verified_at and (k := _phone_key(c.user.phone)):
            g.add_node(f"phone:{k}", kind="phone")
            g.add_edge(f"cand:{c.id}", f"phone:{k}", kind="phone", strength="strong")
    for a in db.query(DuplicateAlert).filter_by(kind="face"):
        node = f"face:{a.id}"
        g.add_node(node, kind="face", similarity=a.similarity)
        for cid in (a.candidate_a_id, a.candidate_b_id):
            g.add_edge(f"cand:{cid}", node, kind="face", strength="strong", similarity=a.similarity)
    for s in db.query(DeviceSighting).all():
        if s.device_hash:
            g.add_node(f"device:{s.device_hash[:12]}", kind="device")
            g.add_edge(f"cand:{s.candidate_id}", f"device:{s.device_hash[:12]}", kind="device", strength="medium")
        if include_weak and s.network_hash:
            g.add_node(f"net:{s.network_hash[:12]}", kind="network")
            g.add_edge(f"cand:{s.candidate_id}", f"net:{s.network_hash[:12]}", kind="network", strength="weak")
    # signal nodes that link nobody are noise
    g.remove_nodes_from([n for n, d in list(g.nodes(data=True)) if d["kind"] != "candidate" and g.degree(n) < 2])
    return g


SIGNAL_LABEL = {"phone": "Same verified mobile number", "face": "Very similar enrolled face", "device": "Same browser", "network": "Same network address"}


def view(db: Session, candidate_id: str, org_id: str | None) -> dict:
    g = build(db)
    focal = f"cand:{candidate_id}"
    if focal not in g:
        return {"nodes": [], "edges": [], "linked": [], "clusterSize": 1, "note": ""}
    org_apps = {}
    if org_id:
        for a in db.query(Application).join(Job).filter(Job.organization_id == org_id):
            org_apps.setdefault(a.candidate_id, a)
    # direct neighbourhood: focal -> signals -> other accounts
    signals = list(g.neighbors(focal))
    nodes, edges, linked = {}, [], {}

    def cand_node(cid: str) -> dict:
        app = org_apps.get(cid)
        cand = db.get(Candidate, cid)
        visible = cid == candidate_id or app is not None
        return {"id": f"cand:{cid}", "kind": "candidate", "focal": cid == candidate_id,
                "label": "This candidate" if cid == candidate_id else (cand.user.full_name if visible else mask(cid)),
                "applicationId": app.id if app and cid != candidate_id else None, "appliedToYourOrg": app is not None and cid != candidate_id}

    nodes[focal] = cand_node(candidate_id)
    for s in signals:
        data = g.nodes[s]
        e = g.edges[focal, s]
        nodes[s] = {"id": s, "kind": data["kind"], "label": SIGNAL_LABEL[data["kind"]] + (f" ({data['similarity']:.2f})" if data.get("similarity") else ""),
                    "strength": e["strength"], "review": data.get("review")}
        edges.append({"source": focal, "target": s, "kind": data["kind"], "strength": e["strength"]})
        for other in g.neighbors(s):
            if other == focal:
                continue
            cid = g.nodes[other]["candidate_id"]
            nodes.setdefault(other, cand_node(cid))
            edges.append({"source": other, "target": s, "kind": data["kind"], "strength": e["strength"]})
            row = linked.setdefault(cid, {"account": nodes[other]["label"], "applicationId": nodes[other]["applicationId"], "signals": []})
            row["signals"].append({"kind": data["kind"], "label": SIGNAL_LABEL[data["kind"]], "strength": e["strength"], "review": data.get("review")})
    for row in linked.values():
        row["strongest"] = max((s["strength"] for s in row["signals"]), key=STRENGTH_ORDER.get)
    # cluster size over strong + medium links only (weak network links would join whole colleges)
    strong = nx.Graph([(u, v) for u, v, d in g.edges(data=True) if d["strength"] != "weak"])
    cluster = {n for n in nx.node_connected_component(strong, focal) if n.startswith("cand:")} if focal in strong else {focal}
    return {
        "nodes": list(nodes.values()), "edges": edges,
        "linked": sorted(linked.values(), key=lambda r: -STRENGTH_ORDER[r["strongest"]]),
        "clusterSize": len(cluster),
        "note": "Linked accounts share a mobile number, face, browser or network. That is a reason to look closer, not a confirmed fraud ring; "
                "shared browsers and networks are weak signals with many innocent explanations.",
    }
