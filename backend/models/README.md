# Face models (OpenCV Zoo, Apache-2.0)

| File | Model | Source |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet face detector | opencv/opencv_zoo `models/face_detection_yunet` |
| `face_recognition_sface_2021dec.onnx` | SFace face recogniser (128-d features) | opencv/opencv_zoo `models/face_recognition_sface` |

`SHA256SUMS` matches the Git LFS object ids published in opencv/opencv_zoo, so these are the official files.
The server checks the hashes before loading. If you replace the files, update `SHA256SUMS`.

`face_recognition_sface_2021dec.onnx` is shipped as `.part1` + `.part2` (upload size limit). The server joins them on
first use and then verifies the joined file against `SHA256SUMS`, so a missing or damaged part is detected.
