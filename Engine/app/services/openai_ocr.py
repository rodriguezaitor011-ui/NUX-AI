"""
OCR module using OpenAI Vision API for image text extraction
"""

import logging
import base64
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class OCRException(Exception):
    """Base exception for OCR errors"""
    pass


class OCRImageTooLarge(OCRException):
    """Image exceeds size limit"""
    pass


class OCRInvalidImage(OCRException):
    """Invalid or corrupted image"""
    pass


class OCRLowQuality(OCRException):
    """Image quality too low for OCR"""
    pass


class OCRBlockedOrEmpty(OCRException):
    """Image blocked by safety system or contains no text"""
    pass


async def ocr_image_async(image_bytes: bytes, mime_type: str) -> str:
    """
    Extract text from image using OpenAI Vision API
    
    Args:
        image_bytes: Raw image bytes
        mime_type: MIME type of the image (e.g., 'image/jpeg')
    
    Returns:
        Extracted text as string
    
    Raises:
        OCRImageTooLarge: If image exceeds size limit
        OCRInvalidImage: If image is invalid or corrupted
        OCRLowQuality: If image quality is too low
        OCRBlockedOrEmpty: If image is blocked or contains no text
        OCRException: For other OCR errors
    """
    # Validate OpenAI API key
    if not settings.OPENAI_API_KEY:
        raise OCRException("OPENAI_API_KEY not configured")
    
    # Validate image size
    if len(image_bytes) > settings.OCR_MAX_IMAGE_SIZE:
        raise OCRImageTooLarge(
            f"Image size ({len(image_bytes)} bytes) exceeds maximum "
            f"allowed size ({settings.OCR_MAX_IMAGE_SIZE} bytes)"
        )
    
    # Encode image to base64
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        raise OCRInvalidImage(f"Failed to encode image: {str(e)}")
    
    # Prepare request to OpenAI
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": settings.OPENAI_OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all text from this image. Preserve formatting, line breaks, and structure as much as possible. If there's handwritten text, transcribe it as accurately as possible. If the image contains no text, respond with 'NO_TEXT_FOUND'."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.1  # Low temperature for accurate transcription
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result["choices"][0]["message"]["content"]
                
                # Check for empty or blocked content
                if not text or text.strip() == "NO_TEXT_FOUND":
                    raise OCRBlockedOrEmpty("No text found in image or image blocked by safety system")
                
                logger.info(f"OCR successful: extracted {len(text)} characters")
                return text.strip()
            
            elif response.status_code == 400:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "Bad request")
                
                if "content policy" in error_msg.lower() or "safety" in error_msg.lower():
                    raise OCRBlockedOrEmpty(f"Image blocked by safety system: {error_msg}")
                elif "invalid" in error_msg.lower() or "corrupt" in error_msg.lower():
                    raise OCRInvalidImage(f"Invalid image: {error_msg}")
                else:
                    raise OCRException(f"OpenAI API error: {error_msg}")
            
            elif response.status_code == 413:
                raise OCRImageTooLarge("Image too large for OpenAI API")
            
            elif response.status_code == 429:
                raise OCRException("Rate limit exceeded for OpenAI API")
            
            elif response.status_code == 401:
                raise OCRException("Invalid OpenAI API key")
            
            else:
                error_msg = f"OpenAI API error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except:
                    pass
                raise OCRException(error_msg)
    
    except httpx.TimeoutException:
        raise OCRException("OCR request timed out")
    
    except httpx.RequestError as e:
        raise OCRException(f"Network error during OCR: {str(e)}")
    
    except Exception as e:
        if isinstance(e, OCRException):
            raise
        raise OCRException(f"Unexpected error during OCR: {str(e)}")


# For backward compatibility
async def process_image_ocr(image_bytes: bytes, mime_type: str) -> str:
    """Alias for ocr_image_async"""
    return await ocr_image_async(image_bytes, mime_type)