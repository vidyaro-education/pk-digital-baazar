# services/qr_service.py
import io
import os
import qrcode
from qrcode.image.pil import PilImage

UPI_ID   = os.getenv("UPI_ID",   "tanudey07@fam")
UPI_NAME = os.getenv("UPI_NAME", "PK Bazar")


def generate_payment_qr(amount: float, order_id: int) -> bytes:
    """Return raw PNG bytes of a UPI payment QR code."""
    qr_content = (
        f"upi://pay?pa={UPI_ID}"
        f"&pn={UPI_NAME}&am={amount:.2f}&tn=Order%23{order_id}"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)

    img: PilImage = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()