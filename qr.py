import qrcode
from urllib.parse import urlencode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask
from PIL import Image, ImageDraw, ImageFont
from config import UPI_ID, UPI_NAME, LABEL

def upi_link(amount: int, note: str) -> str:
    q = urlencode({"pa": UPI_ID, "pn": UPI_NAME, "am": amount, "cu": "INR", "tn": note})
    return f"upi://pay?{q}"

def card(plan: str, amount: int, ref: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(upi_link(amount, f"{LABEL[plan]} {ref}"))
    qr.make(fit=True)
    img = qr.make_image(image_factory=StyledPilImage,
                        module_drawer=RoundedModuleDrawer(radius_ratio=0.85),
                        color_mask=RadialGradiantColorMask(
                            back_color=(255, 255, 255),
                            center_color=(24, 24, 32),
                            edge_color=(60, 120, 255))
                        ).convert("RGB").resize((560, 560), Image.LANCZOS)

    badge = Image.new("RGB", (96, 96), "white")
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle([2, 2, 93, 93], radius=24, outline=(60, 120, 255), width=4)
    bd.text((34, 24), "₹", fill=(20, 20, 30), font=ImageFont.load_default(size=48))
    img.paste(badge, (232, 232))

    c = Image.new("RGB", (720, 900), (14, 14, 20))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle([40, 40, 680, 860], radius=28, fill=(22, 22, 30))
    d.text((72, 78), "Scan to pay", fill=(255, 255, 255), font=ImageFont.load_default(size=34))
    d.text((72, 126), f"{LABEL[plan]} — ₹{amount}", fill=(120, 180, 255), font=ImageFont.load_default(size=28))
    c.paste(img, (80, 190))
    d.text((72, 786), UPI_ID, fill=(235, 235, 245), font=ImageFont.load_default(size=26))
    d.text((72, 822), f"Ref #{ref} · send UTR after paying", fill=(140, 140, 160), font=ImageFont.load_default(size=20))

    path = f"/tmp/upi_{ref}.png"
    c.save(path)
    return path
