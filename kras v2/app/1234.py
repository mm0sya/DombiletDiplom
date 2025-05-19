from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import motor.motor_asyncio
import os
import re
from datetime import datetime, timedelta
import json
import traceback
from bson import ObjectId
import secrets
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import os
from transliterate import translit


