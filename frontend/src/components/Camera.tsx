import { useCallback, useEffect, useRef, useState } from "react";
import { LuCamera, LuCameraOff } from "react-icons/lu";
import { cx } from "./ui";

export type CameraState = "idle" | "starting" | "ready" | "denied" | "unavailable";

/** Webcam access. Frames are captured into memory only; nothing is stored or uploaded here. */
export function useCamera(autoStart = true) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [state, setState] = useState<CameraState>("idle");

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setState("unavailable");
      return;
    }
    setState("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      setState("ready");
    } catch (err) {
      setState((err as DOMException)?.name === "NotAllowedError" ? "denied" : "unavailable");
    }
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setState("idle");
  }, []);

  useEffect(() => {
    if (autoStart) void start();
    return () => streamRef.current?.getTracks().forEach((t) => t.stop());
  }, [autoStart, start]);

  const capture = useCallback((): string | null => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return null;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")?.drawImage(v, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.85);
  }, []);

  return { videoRef, state, start, stop, capture };
}

export function CameraView({ cam, still, className, mirrored = true }: { cam: ReturnType<typeof useCamera>; still?: string | null; className?: string; mirrored?: boolean }) {
  return (
    <div className={cx("relative overflow-hidden rounded-lg bg-[#dfe5e8]", className)}>
      <video ref={cam.videoRef} muted playsInline className={cx("size-full object-cover", mirrored && "-scale-x-100", (still || cam.state !== "ready") && "invisible")} />
      {still && <img src={still} alt="Captured photo" className="absolute inset-0 size-full -scale-x-100 object-cover" />}
      {!still && cam.state !== "ready" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center text-[13px] text-ink-2">
          {cam.state === "denied" || cam.state === "unavailable" ? <LuCameraOff className="size-7 text-ink-3" aria-hidden /> : <LuCamera className="size-7 text-ink-3" aria-hidden />}
          {cam.state === "denied"
            ? "Camera access is blocked. Allow it from the address bar, then reload."
            : cam.state === "unavailable"
              ? "No camera found. Use localhost or HTTPS with a webcam connected."
              : cam.state === "starting"
                ? "Starting camera…"
                : (
                  <button onClick={() => void cam.start()} className="rounded-md bg-white px-3 py-1.5 font-medium text-brand-700 shadow-sm">
                    Turn on camera
                  </button>
                )}
        </div>
      )}
    </div>
  );
}
