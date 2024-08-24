# app/utils/scheduling.py

import datetime
import json
import logging
import os
import random
import re

from apscheduler.triggers.cron import CronTrigger
from dateutil import parser
from flask_apscheduler import APScheduler
from PIL import Image, ImageDraw, ImageFont
from transformers import CLIPProcessor, CLIPModel

from app.config import DEBUG, SCREENSHOT_DIRECTORY, SUMMARIES_DIRECTORY, VIDEO_DIRECTORY
from app.utils.db import SessionLocal
from app.models import Summary

from .detect import calculate_difference_fast
from .image_processing import chatgpt_compare
from .llm import summarize
from .screenshots import capture_or_download, remove_background, add_timestamp
from .template_manager import get_template, get_templates, save_template

scheduler = APScheduler()