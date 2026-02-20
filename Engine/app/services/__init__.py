from app.services.openai_service import openai_service

__all__ = ["openai_service"]

# OCR de apuntes (Gemini Vision) - import bajo demanda para no requerir GEMINI_API_KEY al arrancar
# from app.services.gemini_ocr import extract_text_from_image, ocr_image_async, OCRException, OCRLowQuality

# OCR de apuntes (Gemini Vision) - import bajo demanda para no requerir GEMINI_API_KEY al arrancar
# from app.services.gemini_ocr import extract_text_from_image, ocr_image_async, OCRException, OCRLowQuality
