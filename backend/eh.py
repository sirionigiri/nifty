import numpy as np
import matplotlib.pyplot as plt
from openpyxl import Workbook
from openpyxl.drawing.image import Image

# Values
min_val = 0.20
current_val = 1.08
max_val = 1.60

# Normalize
pos = (current_val - min_val) / (max_val - min_val)

# Create gauge image
fig, ax = plt.subplots(figsize=(8, 1.5))

# Gradient bar
gradient = np.linspace(0, 1, 500).reshape(1, -1)
ax.imshow(
    gradient,
    aspect="auto",
    extent=[0, 1, 0, 0.25]
)

# Arrow
ax.scatter(
    pos,
    0.35,
    marker="v",
    s=800,
    color="black"
)

# Labels
ax.text(0, 0.5, f"{min_val:.2f}", ha="center")
ax.text(pos, 0.5, f"{current_val:.2f}", ha="center")
ax.text(1, 0.5, f"{max_val:.2f}", ha="center")

ax.set_xlim(-0.05, 1.05)
ax.set_ylim(-0.05, 0.7)
ax.axis("off")

plt.savefig("gauge.png", bbox_inches="tight", dpi=150)
plt.close()

# Export to Excel
wb = Workbook()
ws = wb.active
ws.title = "Dashboard"

img = Image("gauge.png")
ws.add_image(img, "B2")

wb.save("dashboard.xlsx")