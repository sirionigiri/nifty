import { forceSimulation, forceCollide, forceX, forceY, forceManyBody } from "d3-force"

interface Point {
  x: number
  y: number
  text: string
  color: string
}

interface LayoutOptions {
  plotWidthPx: number
  plotHeightPx: number
  xRange: [number, number]
  yRange: [number, number]
  fontSize?: number
  fontWeight?: number
  markerRadiusPx?: number
  iterations?: number
}

let measureCanvas: HTMLCanvasElement | null = null

// Real text measurement instead of a char-count heuristic — matters a lot
// once label lengths vary ("NIFTY 50" vs "NIFTY MIDSMALLCAP400 50:50").
function measureText(text: string, fontSize: number, fontWeight: number) {
  if (typeof document === "undefined") return text.length * fontSize * 0.6
  if (!measureCanvas) measureCanvas = document.createElement("canvas")
  const ctx = measureCanvas.getContext("2d")!
  ctx.font = `${fontWeight} ${fontSize}px sans-serif`
  return ctx.measureText(text).width
}

interface SimNode {
  index: number
  // anchor = the actual data point, fixed
  anchorX: number
  anchorY: number
  // x/y = the label's current (simulated) center position
  x: number
  y: number
  vx: number
  vy: number
  width: number
  height: number
  text: string
  color: string
}

export function computeLabelLayout(points: Point[], opts: LayoutOptions) {
  const { plotWidthPx, plotHeightPx, xRange, yRange } = opts
  const fontSize = opts.fontSize ?? 11
  const fontWeight = opts.fontWeight ?? 700
  const markerR = opts.markerRadiusPx ?? 9
  const iterations = opts.iterations ?? 300
  const labelH = fontSize + 6
  const initialOffset = 22 // start labels slightly above their point

  const px = (x: number) => ((x - xRange[0]) / (xRange[1] - xRange[0])) * plotWidthPx
  const py = (y: number) => plotHeightPx - ((y - yRange[0]) / (yRange[1] - yRange[0])) * plotHeightPx

  // Build sim nodes for labels, starting just above each point
  const nodes: SimNode[] = points.map((p, i) => {
    const anchorX = px(p.x)
    const anchorY = py(p.y)
    return {
      index: i,
      anchorX,
      anchorY,
      x: anchorX,
      y: anchorY - initialOffset,
      vx: 0,
      vy: 0,
      width: measureText(p.text, fontSize, fontWeight) + 10,
      height: labelH,
      text: p.text,
      color: p.color,
    }
  })

  // Also treat the raw points themselves as fixed obstacles labels must
  // avoid — collide radius covers the marker.
  const pointObstacles = points.map((p, i) => ({
    x: px(p.x),
    y: py(p.y),
    r: markerR + 4,
  }))

  const sim = forceSimulation(nodes as any)
    .force("charge", forceManyBody().strength(-2)) // gentle mutual repulsion
    // pull each label back toward its own anchor (spring)
    .force(
      "x",
      forceX<SimNode>((d:any) => d.anchorX).strength(0.06)
    )
    .force(
      "y",
      forceY<SimNode>((d:any) => d.anchorY - initialOffset).strength(0.06)
    )
    // rectangle-ish collision between labels, approximated via radius
    .force(
      "collide",
      forceCollide<SimNode>((d:any) => Math.max(d.width, d.height) / 2 + 2)
        .strength(0.9)
        .iterations(3)
    )
    .stop()

  // Custom per-tick step: after d3-force's own forces, nudge labels away
  // from point obstacles (not just other labels) using rectangle-vs-circle
  // separation, since forceCollide only knows about the label nodes.
  for (let i = 0; i < iterations; i++) {
    sim.tick()
    for (const n of nodes) {
      for (const obs of pointObstacles) {
        const dx = n.x - obs.x
        const dy = n.y - obs.y
        const halfW = n.width / 2 + obs.r
        const halfH = n.height / 2 + obs.r
        if (Math.abs(dx) < halfW && Math.abs(dy) < halfH) {
          // push out along the axis of minimum overlap
          const overlapX = halfW - Math.abs(dx)
          const overlapY = halfH - Math.abs(dy)
          if (overlapX < overlapY) {
            n.x += overlapX * Math.sign(dx || 1)
          } else {
            n.y += overlapY * Math.sign(dy || 1)
          }
        }
      }
      // keep labels within plot bounds
      n.x = Math.min(Math.max(n.x, n.width / 2), plotWidthPx - n.width / 2)
      n.y = Math.min(Math.max(n.y, n.height / 2), plotHeightPx - n.height / 2)
    }
  }

  return nodes.map((n, i) => {
    const p = points[i]
    return {
      x: p.x,
      y: p.y,
      xref: "x" as const,
      yref: "y" as const,
      text: p.text,
      showarrow: true,
      arrowhead: 0,
      arrowwidth: 1,
      arrowcolor: "#94a3b8",
      standoff: markerR + 2,
      // Plotly annotations position labels via ax/ay pixel offsets
      // *relative to the anchor point*, so convert back from absolute sim coords.
      ax: n.x - n.anchorX,
      ay: n.y - n.anchorY,
      font: { size: fontSize, color: p.color, weight: fontWeight },
      bgcolor: "rgba(255,255,255,0.85)",
      borderpad: 1,
    }
  })
}