import { useEffect, useRef, useState } from "react"
import { Lock, Loader2, Server, Shield, FileKey, ChevronDown } from "lucide-react"
import { ApexFlowLogo } from "@/components/icons/ApexFlowLogo"
import { useAuth } from "@/contexts/AuthContext"

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true">
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  )
}

interface Node {
  x: number
  y: number
  vx: number
  vy: number
}

function NeuralBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let animationId: number
    const nodeCount = 80
    const connectionDistance = 180
    const nodes: Node[] = []

    function resize() {
      const dpr = window.devicePixelRatio || 1
      canvas!.width = window.innerWidth * dpr
      canvas!.height = window.innerHeight * dpr
      canvas!.style.width = `${window.innerWidth}px`
      canvas!.style.height = `${window.innerHeight}px`
      ctx!.scale(dpr, dpr)
    }
    resize()
    window.addEventListener("resize", resize)

    // Initialize nodes
    for (let i = 0; i < nodeCount; i++) {
      nodes.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
      })
    }

    function draw() {
      const w = window.innerWidth
      const h = window.innerHeight
      ctx!.clearRect(0, 0, w, h)

      // Update positions
      for (const node of nodes) {
        node.x += node.vx
        node.y += node.vy

        if (node.x < 0 || node.x > w) node.vx *= -1
        if (node.y < 0 || node.y > h) node.vy *= -1
      }

      // Draw connections
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)

          if (dist < connectionDistance) {
            const opacity = (1 - dist / connectionDistance) * 0.25
            ctx!.beginPath()
            ctx!.moveTo(nodes[i].x, nodes[i].y)
            ctx!.lineTo(nodes[j].x, nodes[j].y)
            ctx!.strokeStyle = `rgba(71, 85, 105, ${opacity})`
            ctx!.lineWidth = 0.6
            ctx!.stroke()
          }
        }
      }

      // Draw nodes with glow
      for (const node of nodes) {
        // Outer glow
        ctx!.beginPath()
        ctx!.arc(node.x, node.y, 5, 0, Math.PI * 2)
        ctx!.fillStyle = "rgba(71, 85, 105, 0.06)"
        ctx!.fill()

        // Core dot
        ctx!.beginPath()
        ctx!.arc(node.x, node.y, 2, 0, Math.PI * 2)
        ctx!.fillStyle = "rgba(71, 85, 105, 0.4)"
        ctx!.fill()
      }

      animationId = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener("resize", resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 z-[1] pointer-events-none"
      aria-hidden="true"
    />
  )
}

function StatusFooter() {
  const [isOpen, setIsOpen] = useState(false)

  const statusItems = [
    { icon: Server, label: "Internal Sources", detail: "VPC Connections Active" },
    { icon: Shield, label: "Data Compliance", detail: "PII Redaction Enabled" },
    { icon: FileKey, label: "Secure Export", detail: "Watermarking Active" },
  ]

  return (
    <footer className="absolute bottom-0 w-full z-10 border-t border-border/30 bg-background/80 backdrop-blur-md py-4">
      <div className="container mx-auto px-6 max-w-4xl">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-full flex flex-col items-center cursor-pointer outline-none opacity-40 hover:opacity-80 transition-opacity"
        >
          <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground uppercase tracking-[0.2em]">
            <span>System Status: Operational</span>
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
            />
          </div>
        </button>

        {isOpen && (
          <div className="grid md:grid-cols-3 gap-8 pt-8 pb-4 animate-fade-up">
            {statusItems.map((item) => (
              <div
                key={item.label}
                className="text-center space-y-2 p-4 rounded-lg hover:bg-muted/50 transition-colors"
              >
                <item.icon className="h-5 w-5 mx-auto text-muted-foreground" />
                <h3 className="font-sans font-semibold text-sm text-foreground">{item.label}</h3>
                <p className="text-[11px] text-muted-foreground leading-relaxed">{item.detail}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </footer>
  )
}

export function SignInScreen() {
  const auth = useAuth()
  const [isSigningIn, setIsSigningIn] = useState(false)

  const handleSignIn = async () => {
    setIsSigningIn(true)
    try {
      await auth.signIn()
    } finally {
      setIsSigningIn(false)
    }
  }

  return (
    <div className="relative flex flex-col h-screen bg-background overflow-hidden">
      {/* Animated neural network background */}
      <NeuralBackground />

      {/* Subtle radial gradient overlay */}
      <div
        className="absolute inset-0 z-[2] pointer-events-none"
        aria-hidden="true"
        style={{
          backgroundImage:
            "radial-gradient(circle at 15% 50%, hsl(var(--primary) / 0.06) 0%, transparent 25%), radial-gradient(circle at 85% 30%, hsl(var(--primary) / 0.06) 0%, transparent 25%)",
        }}
      />

      {/* Top-edge fade for depth */}
      <div
        className="absolute inset-0 z-[3] pointer-events-none"
        aria-hidden="true"
        style={{
          background:
            "linear-gradient(to bottom, hsl(var(--background)) 0%, transparent 15%, transparent 85%, hsl(var(--background)) 100%)",
        }}
      />

      {/* Secure Portal badge */}
      <nav className="absolute top-0 w-full z-20 px-8 py-6">
        <div className="container mx-auto flex justify-end">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-background/50 backdrop-blur-sm border border-border/40 text-muted-foreground shadow-elevation-1">
            <Lock className="h-3 w-3" />
            <span className="hidden sm:inline text-[10px] font-semibold tracking-[0.15em] uppercase">
              Secure Portal
            </span>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-grow flex items-center justify-center relative z-10 px-6 py-20">
        <div className="w-full max-w-3xl text-center flex flex-col items-center justify-center min-h-[60vh]">
          <div className="space-y-16 w-full animate-fade-up">
            {/* Logo + Hero Typography */}
            <div className="flex flex-col items-center space-y-8">
              <div className="w-24 h-24 bg-gradient-to-br from-slate-800 to-black dark:from-white dark:to-slate-200 rounded-3xl flex items-center justify-center shadow-2xl mb-2 transform hover:scale-105 transition-transform duration-500">
                <ApexFlowLogo className="h-12 w-12 text-white dark:text-slate-900" />
              </div>

              <div className="space-y-4">
                <h1
                  className="text-8xl md:text-9xl font-bold text-foreground tracking-tighter leading-none select-none"
                  style={{ fontFamily: "'Playfair Display', 'Instrument Serif', serif" }}
                >
                  Cortex
                </h1>
                <p
                  className="text-2xl md:text-3xl text-muted-foreground font-light tracking-wide"
                  style={{ fontFamily: "'Playfair Display', 'Instrument Serif', serif", fontStyle: "italic" }}
                >
                  Enterprise Intelligence
                </p>
                <p className="text-lg md:text-xl tracking-[0.2em] uppercase text-muted-foreground mt-3">
                  Think deeper. Work smarter.
                </p>
              </div>
            </div>

            {/* Sign-in button + credit */}
            <div className="space-y-12 max-w-md mx-auto pt-4 w-full">
              <button
                onClick={() => void handleSignIn()}
                disabled={isSigningIn}
                className="group relative w-full flex items-center justify-center gap-4 bg-card border border-border/60 text-foreground px-8 py-5 rounded-xl hover:bg-muted/50 hover:border-border transition-all shadow-lg hover:shadow-xl duration-300 transform hover:-translate-y-0.5 disabled:opacity-60 disabled:pointer-events-none"
              >
                {isSigningIn ? (
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                ) : (
                  <GoogleIcon />
                )}
                <span className="font-sans font-semibold text-xl tracking-tight">
                  {isSigningIn ? "Signing in..." : "Sign in with Google"}
                </span>
                <div className="absolute inset-0 rounded-xl ring-2 ring-border/40 opacity-0 group-hover:opacity-100 group-hover:scale-[1.02] transition-all duration-300 pointer-events-none" />
              </button>

              {auth.lastError && (
                <p className="text-sm text-destructive text-center -mt-8">
                  {auth.lastError}
                </p>
              )}

              {/* Gradient divider + credit */}
              <div className="relative pt-6">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-border to-transparent" />
                <div className="flex flex-col items-center gap-2 mt-6">
                  <p className="text-sm md:text-base font-sans font-bold tracking-[0.15em] text-foreground uppercase">
                    Designed &amp; Developed by Pravin Gadekar
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* System status footer */}
      <StatusFooter />
    </div>
  )
}
