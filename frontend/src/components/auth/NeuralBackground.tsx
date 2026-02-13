import { useEffect, useRef } from "react"

const NODE_COUNT = 50
const CONNECTION_DISTANCE = 150
const MOUSE_RADIUS = 200
const MOUSE_PUSH_STRENGTH = 0.8

interface Node {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  baseAlpha: number
}

function createNodes(width: number, height: number): Node[] {
  return Array.from({ length: NODE_COUNT }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.4,
    vy: (Math.random() - 0.5) * 0.4,
    radius: Math.random() * 2 + 1.5,
    baseAlpha: Math.random() * 0.3 + 0.2,
  }))
}

export function NeuralBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const nodesRef = useRef<Node[]>([])
  const mouseRef = useRef({ x: -1000, y: -1000 })
  const animFrameRef = useRef<number>(0)
  const sizeRef = useRef({ w: 0, h: 0 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1

    function resize() {
      const w = window.innerWidth
      const h = window.innerHeight
      canvas!.width = w * dpr
      canvas!.height = h * dpr
      canvas!.style.width = `${w}px`
      canvas!.style.height = `${h}px`
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)

      if (sizeRef.current.w === 0) {
        nodesRef.current = createNodes(w, h)
      } else {
        const sx = w / sizeRef.current.w
        const sy = h / sizeRef.current.h
        for (const node of nodesRef.current) {
          node.x *= sx
          node.y *= sy
        }
      }
      sizeRef.current = { w, h }
    }

    resize()
    window.addEventListener("resize", resize)

    function onMouseMove(e: MouseEvent) {
      mouseRef.current = { x: e.clientX, y: e.clientY }
    }

    function onMouseLeave() {
      mouseRef.current = { x: -1000, y: -1000 }
    }

    window.addEventListener("mousemove", onMouseMove)
    window.addEventListener("mouseleave", onMouseLeave)

    function isDark() {
      return document.documentElement.classList.contains("dark")
    }

    function draw() {
      const { w, h } = sizeRef.current
      const dark = isDark()
      const nodes = nodesRef.current
      const mouse = mouseRef.current

      ctx!.clearRect(0, 0, w, h)

      // Colors from the existing sign-in palette
      const nodeColor = dark ? [100, 116, 139] : [148, 163, 184] // slate-500 / slate-400
      const lineColor = dark ? [71, 85, 105] : [203, 213, 225]   // slate-600 / slate-300
      const glowColor = dark ? [30, 58, 138] : [30, 58, 138]     // blue-900

      // Update node positions
      for (const node of nodes) {
        // Mouse repulsion
        const dx = node.x - mouse.x
        const dy = node.y - mouse.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < MOUSE_RADIUS && dist > 0) {
          const force = (1 - dist / MOUSE_RADIUS) * MOUSE_PUSH_STRENGTH
          node.vx += (dx / dist) * force
          node.vy += (dy / dist) * force
        }

        // Damping
        node.vx *= 0.99
        node.vy *= 0.99

        // Clamp velocity
        const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy)
        if (speed > 1.2) {
          node.vx = (node.vx / speed) * 1.2
          node.vy = (node.vy / speed) * 1.2
        }

        node.x += node.vx
        node.y += node.vy

        // Wrap around edges with padding
        if (node.x < -20) node.x = w + 20
        if (node.x > w + 20) node.x = -20
        if (node.y < -20) node.y = h + 20
        if (node.y > h + 20) node.y = -20
      }

      // Draw connections
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)

          if (dist < CONNECTION_DISTANCE) {
            const alpha = (1 - dist / CONNECTION_DISTANCE) * 0.35
            ctx!.beginPath()
            ctx!.moveTo(nodes[i].x, nodes[i].y)
            ctx!.lineTo(nodes[j].x, nodes[j].y)
            ctx!.strokeStyle = `rgba(${lineColor[0]}, ${lineColor[1]}, ${lineColor[2]}, ${alpha})`
            ctx!.lineWidth = 0.8
            ctx!.stroke()
          }
        }
      }

      // Draw nodes
      for (const node of nodes) {
        // Glow
        const gradient = ctx!.createRadialGradient(
          node.x, node.y, 0,
          node.x, node.y, node.radius * 6
        )
        gradient.addColorStop(0, `rgba(${glowColor[0]}, ${glowColor[1]}, ${glowColor[2]}, ${node.baseAlpha * 0.15})`)
        gradient.addColorStop(1, `rgba(${glowColor[0]}, ${glowColor[1]}, ${glowColor[2]}, 0)`)
        ctx!.beginPath()
        ctx!.arc(node.x, node.y, node.radius * 6, 0, Math.PI * 2)
        ctx!.fillStyle = gradient
        ctx!.fill()

        // Node dot
        ctx!.beginPath()
        ctx!.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(${nodeColor[0]}, ${nodeColor[1]}, ${nodeColor[2]}, ${node.baseAlpha + 0.3})`
        ctx!.fill()
      }

      animFrameRef.current = requestAnimationFrame(draw)
    }

    animFrameRef.current = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(animFrameRef.current)
      window.removeEventListener("resize", resize)
      window.removeEventListener("mousemove", onMouseMove)
      window.removeEventListener("mouseleave", onMouseLeave)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: 0 }}
    />
  )
}
