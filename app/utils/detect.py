# app/utils/detect.py

import logging

import numpy as np
from PIL import Image


def calculate_difference_fast(image_path_a, image_path_b, downsample_size=(100, 100)):
    """Compute a quick dissimilarity score between two images.

    The function downsamples the images and calculates the mean squared
    difference. The result is normalized to ``0`` for identical images and
    ``1`` for completely different 8-bit grayscale images.

    Args:
        image_path_a (str): The file path to the first image.
        image_path_b (str): The file path to the second image.
        downsample_size (tuple): The new size for downsampling the images before comparison.

    Returns:
        float: Dissimilarity score between the downsampled images. ``0`` means
        the images are identical.
    """
    try:
        # Open and resize the images
        image_a = Image.open(image_path_a).resize(downsample_size).convert("L")
        image_b = Image.open(image_path_b).resize(downsample_size).convert("L")

        # Convert images to float arrays for calculation
        array_a = np.array(image_a, dtype=np.float32)
        array_b = np.array(image_b, dtype=np.float32)

        # Compute mean squared error and normalize to the range [0, 1]
        mse = np.mean((array_a - array_b) ** 2)
        normalized = mse / (255.0**2)
        return float(min(1.0, normalized))
    except Exception as e:
        # Handle exceptions (e.g., file not found, invalid image format)
        logging.error("Error calculating difference: %s", e)
        return None
