"""Hand-rolled SVG chart geometry for Tatmaq Books (no external chart libraries)."""


def _scale(vals, w, h, pad_top=8, pad_bottom=6):
    flat = [v for v in vals]
    vmax = max(flat + [0]) or 1
    vmin = min(flat + [0])
    if vmax == vmin:
        vmax = vmin + 1
    span = vmax - vmin

    def y_of(v):
        return round(pad_top + (h - pad_top - pad_bottom) * (1 - (v - vmin) / span), 1)

    return vmax, vmin, y_of


def _path(values, w, h, y_of, pad_x=4):
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = pad_x + (i * (w - 2 * pad_x) / (n - 1)) if n > 1 else w / 2
        pts.append((round(x, 1), y_of(v)))
    d = "M" + " L".join(f"{x},{y}" for x, y in pts)
    return d, pts


def area_chart(series, w=640, h=220, pad_x=4):
    """series: list of {'name': str, 'color': str, 'values': [..]}; shared scale. Returns dict."""
    allvals = [v for s in series for v in s["values"]]
    vmax, vmin, y_of = _scale(allvals, w, h)
    out = {"paths": [], "w": w, "h": h, "vmax": vmax, "vmin": vmin,
           "ticks": [round(vmax * f, 0) for f in (1, 0.66, 0.33, 0)]}
    for s in series:
        d, pts = _path(s["values"], w, h, y_of, pad_x)
        area = d + f" L{pts[-1][0]},{h} L{pts[0][0]},{h} Z"
        out["paths"].append({"name": s["name"], "color": s["color"], "path": d,
                             "area": area, "pts": pts, "values": s["values"]})
    return out


def bar_chart(values, w=640, h=200, pad_x=6):
    vmax, vmin, _ = _scale(values, w, h)
    top = max(vmax, 0)
    bottom = min(vmin, 0)
    span = (top - bottom) or 1
    zero_y = 8 + (h - 14) * (top / span)
    n = len(values)
    slot = w / max(n, 1)
    bw = slot * 0.52
    bars = []
    for i, v in enumerate(values):
        x = i * slot + (slot - bw) / 2
        yv = 8 + (h - 14) * (1 - (v - bottom) / span)
        y0 = min(yv, zero_y)
        hh = max(abs(zero_y - yv), 1.5)
        bars.append({"x": round(x, 1), "y": round(y0, 1), "w": round(bw, 1), "h": round(hh, 1),
                     "value": v, "positive": v >= 0})
    return {"bars": bars, "zero_y": round(zero_y, 1), "w": w, "h": h,
            "vmax": vmax, "vmin": vmin}


def sparkline(values, w=120, h=34):
    if not values:
        return {"path": "", "area": "", "w": w, "h": h}
    vmax, vmin, y_of = _scale(values, w, h, 4, 4)
    d, pts = _path(values, w, h, y_of, 2)
    area = d + f" L{pts[-1][0]},{h} L{pts[0][0]},{h} Z"
    return {"path": d, "area": area, "last": pts[-1], "w": w, "h": h}


def donut(items, size=180, thickness=26):
    """items: [{name, value, color}] -> segments with dasharray."""
    total = sum(i["value"] for i in items) or 1
    r = (size - thickness) / 2
    circ = 2 * 3.141592653589793 * r
    segs, acc = [], 0.0
    for it in items:
        frac = it["value"] / total
        segs.append({**it, "dash": round(frac * circ, 2), "gap": round(circ - frac * circ, 2),
                     "offset": round(-acc * circ, 2), "pct": round(frac * 100, 1)})
        acc += frac
    return {"segments": segs, "size": size, "r": r, "circ": round(circ, 2),
            "thickness": thickness, "total": total,
            "center": size / 2}


def gauge(score, size=132, thickness=11):
    """Semi-circular arc gauge 0-100."""
    r = (size - thickness) / 2
    circ = 3.141592653589793 * r  # half circle
    frac = max(0, min(100, score)) / 100
    color = "#22c58b" if score >= 70 else ("#f5a524" if score >= 45 else "#ff5c7a")
    return {"r": r, "circ": round(circ, 2), "dash": round(circ * frac, 2),
            "gap": round(circ - circ * frac, 2), "color": color, "size": size,
            "thickness": thickness, "center": size / 2, "w": size, "h": size / 2 + 14}
