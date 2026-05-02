"""Patch MegaDetector v5 ONNX so its output matches YOLOv8 format.

Frigate's `yolo-generic` post-processor expects:
    [batch, 4 + num_classes, num_anchors]  (YOLOv8)

MegaDetector v5 (YOLOv5 architecture) emits:
    [batch, num_anchors, 4 + 1 + num_classes]
    where col 4 is objectness and cols 5+ are class probabilities.

We splice in nodes at the output of the existing graph:
    1. Split [1, 25500, 8] along last dim into:
         bbox    [1, 25500, 4]
         obj     [1, 25500, 1]
         classes [1, 25500, 3]
    2. scores = obj * classes  (broadcast)         [1, 25500, 3]
    3. concat[bbox, scores] along last dim         [1, 25500, 7]
    4. transpose [0, 2, 1]                          [1, 7, 25500]

The final tensor is YOLOv8-format and Frigate parses it correctly.

Usage:
    python patch_megadetector_to_yolov8.py \\
        model_cache/megadetector.onnx \\
        model_cache/megadetector_yolov8.onnx
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def patch(in_path: Path, out_path: Path) -> None:
    model = onnx.load(str(in_path))
    graph = model.graph

    if len(graph.output) != 1:
        raise RuntimeError(f"expected exactly one output, got {len(graph.output)}")
    orig = graph.output[0]
    orig_name = orig.name
    shape = [d.dim_value for d in orig.type.tensor_type.shape.dim]
    if len(shape) != 3 or shape[2] != 8:
        raise RuntimeError(f"expected output [B, A, 8] (YOLOv5x w/ 3 classes); got {shape}")
    batch, anchors, _ = shape  # 1, 25500, 8
    num_classes = 3

    # --- Op nodes -----------------------------------------------------
    # Split [1, 25500, 8] → 3 tensors along axis=2 using opset-11
    # attribute form (required because the model is opset 12 and
    # Split with input-form sizes only landed in opset 13).
    split_node = helper.make_node(
        "Split",
        inputs=[orig_name],
        outputs=["md_bbox", "md_obj", "md_cls"],
        axis=2,
        split=[4, 1, num_classes],
    )

    # scores = obj * cls   (obj broadcasts: [1, 25500, 1] * [1, 25500, 3] → [1, 25500, 3])
    mul_node = helper.make_node("Mul", ["md_obj", "md_cls"], ["md_scores"])

    # combined = concat([bbox, scores], axis=2)  →  [1, 25500, 7]
    concat_node = helper.make_node(
        "Concat",
        inputs=["md_bbox", "md_scores"],
        outputs=["md_combined"],
        axis=2,
    )

    # transposed = transpose(combined, perm=[0, 2, 1])  →  [1, 7, 25500]
    transpose_node = helper.make_node(
        "Transpose",
        inputs=["md_combined"],
        outputs=["md_yolov8_output"],
        perm=[0, 2, 1],
    )

    # --- Wire into graph ---------------------------------------------
    graph.node.extend([
        split_node,
        mul_node,
        concat_node,
        transpose_node,
    ])

    # Replace graph output. We keep the same name "output" so Frigate's
    # detector code (which doesn't know the output name) finds it.
    new_output = helper.make_tensor_value_info(
        "md_yolov8_output",
        TensorProto.FLOAT,
        [batch, 4 + num_classes, anchors],
    )
    graph.output.pop()
    graph.output.append(new_output)

    # Validate. If shape inference disagrees, surface that error early.
    onnx.checker.check_model(model, full_check=True)

    onnx.save(model, str(out_path))
    print(f"Wrote {out_path}")
    print(f"  Original output: {orig_name} {shape}")
    print(f"  New output:      md_yolov8_output [{batch}, {4 + num_classes}, {anchors}]")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: patch_megadetector_to_yolov8.py <in.onnx> <out.onnx>")
        sys.exit(1)
    patch(Path(sys.argv[1]), Path(sys.argv[2]))
