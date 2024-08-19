# app/utils/detect.py

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim


def calculate_difference_fast(image_path_a, image_path_b, downsample_size=(100, 100)):
    """
    Calculate the difference between two images using the Structural Similarity Index (SSIM).

    Args:
        image_path_a (str): The file path to the first image.
        image_path_b (str): The file path to the second image.
        downsample_size (tuple): The new size for downsampling the images before comparison.

    Returns:
        float: The SSIM index between the two downsampled images. Values closer to 0 indicate greater dissimilarity.
    """
    try:
        # Open and resize the images
        image_a = Image.open(image_path_a).resize(downsample_size).convert("L")
        image_b = Image.open(image_path_b).resize(downsample_size).convert("L")

        # Convert images to arrays
        array_a = np.array(image_a)
        array_b = np.array(image_b)

        # Calculate SSIM
        ssim_index, _ = ssim(array_a, array_b, full=True)
        return 1 - ssim_index  # Convert to a dissimilarity measure
    except Exception as e:
        # Handle exceptions (e.g., file not found, invalid image format)
        print(f"Error: {e}")
        return None
