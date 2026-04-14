"""Build HuggingFace datasets from collected training samples."""

import json
import os
from pathlib import Path

from a1.common.logging import get_logger
from config.settings import settings

log = get_logger("training.dataset")


def build_dataset(samples: list[dict], output_dir: str | None = None) -> dict:
    """Convert collected samples into train/val/test splits saved as JSONL files.

    Args:
        samples: list of {"messages": [...]} dicts
        output_dir: where to save the dataset files

    Returns:
        dict with paths: {"train": path, "val": path, "test": path, "total": int}
    """
    if not samples:
        raise ValueError("No samples to build dataset from")

    output_dir = output_dir or os.path.join(settings.training_output_dir, "datasets", "latest")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Shuffle deterministically
    import random

    rng = random.Random(42)
    rng.shuffle(samples)

    # Split: 80/10/10
    n = len(samples)
    train_end = int(n * 0.8)
    val_end = int(n * 0.9)

    splits = {
        "train": samples[:train_end],
        "val": samples[train_end:val_end],
        "test": samples[val_end:],
    }

    paths = {}
    for split_name, split_data in splits.items():
        path = os.path.join(output_dir, f"{split_name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for sample in split_data:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        paths[split_name] = path
        log.info(f"Wrote {len(split_data)} samples to {path}")

    # Save metadata
    meta_path = os.path.join(output_dir, "metadata.json")
    metadata = {
        "total_samples": n,
        "train_samples": len(splits["train"]),
        "val_samples": len(splits["val"]),
        "test_samples": len(splits["test"]),
    }
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    paths["total"] = n
    return paths


def load_dataset_for_training(dataset_dir: str) -> tuple:
    """Load dataset files for HuggingFace trainer.

    Returns (train_dataset, val_dataset) as HuggingFace Dataset objects.
    """
    from datasets import load_dataset

    train_ds = load_dataset(
        "json", data_files=os.path.join(dataset_dir, "train.jsonl"), split="train"
    )
    val_ds = load_dataset("json", data_files=os.path.join(dataset_dir, "val.jsonl"), split="train")

    return train_ds, val_ds
