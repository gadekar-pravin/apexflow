import { useState } from "react"
import { BrainCog, ChevronDown, FileKey, Loader2, Lock, Server, Shield } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { NeuralBackground } from "./NeuralBackground"
import "./SignInScreen.css"

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-7 w-7" aria-hidden="true">
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

function StatusFooter() {
  return (
    <section className="absolute bottom-0 w-full z-10 border-t border-border/50 bg-card/75 backdrop-blur-md py-6">
      <details className="group container mx-auto px-6 max-w-4xl">
        <summary className="list-none flex flex-col items-center cursor-pointer outline-none opacity-50 hover:opacity-100 transition-opacity">
          <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
            <span>System Status: Operational</span>
            <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
          </div>
        </summary>
        <div className="grid md:grid-cols-3 gap-8 pt-8 pb-4 animate-fade-in">
          {[
            { icon: Server, title: "Internal Sources", desc: "VPC Connections Active" },
            { icon: Shield, title: "Data Compliance", desc: "PII Redaction Enabled" },
            { icon: FileKey, title: "Secure Export", desc: "Watermarking Active" },
          ].map((item) => (
            <div
              key={item.title}
              className="text-center space-y-2 p-4 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <item.icon className="h-6 w-6 text-primary/70 mx-auto" />
              <h3 className="font-semibold text-sm text-foreground" style={{ fontFamily: "\"Manrope\", sans-serif" }}>
                {item.title}
              </h3>
              <p className="text-[11px] text-muted-foreground leading-relaxed" style={{ fontFamily: "\"Manrope\", sans-serif" }}>
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </details>
    </section>
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
    <div className="relative flex flex-col min-h-screen overflow-hidden bg-background text-foreground signin-zen-bg">
      <NeuralBackground />

      <nav className="absolute top-0 w-full z-20 px-8 py-6">
        <div className="container mx-auto flex justify-between items-center">
          <div className="hidden md:block" />
          <div className="flex items-center space-x-6 text-xs font-medium text-muted-foreground uppercase tracking-widest ml-auto md:ml-0">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-card/70 backdrop-blur-sm border border-primary/20 text-primary shadow-sm">
              <Lock className="h-3.5 w-3.5" />
              <span className="hidden sm:inline text-[10px] font-semibold tracking-wider" style={{ fontFamily: "\"Manrope\", sans-serif" }}>
                Secure Portal
              </span>
            </div>
          </div>
        </div>
      </nav>

      <main className="flex-grow flex items-center justify-center relative px-6 py-20 z-10">
        <div className="w-full max-w-3xl text-center flex flex-col items-center justify-center min-h-[60vh]">
          <div className="space-y-16 w-full relative">
            <div className="flex flex-col items-center space-y-8 animate-fade-up">
              <div className="w-24 h-24 bg-gradient-to-br from-primary to-primary/80 rounded-3xl flex items-center justify-center text-primary-foreground shadow-2xl mb-2 transform hover:scale-105 transition-transform duration-500">
                <BrainCog className="h-14 w-14" strokeWidth={1.9} />
              </div>

              <div className="space-y-4">
                <h1
                  className="text-8xl md:text-9xl font-bold text-foreground tracking-tighter leading-none select-none drop-shadow-sm"
                  style={{ fontFamily: "\"Manrope\", sans-serif" }}
                >
                  Cortex
                </h1>
                <p
                  className="italic text-3xl text-muted-foreground font-light tracking-wide"
                  style={{ fontFamily: "\"Manrope\", sans-serif" }}
                >
                  Enterprise Intelligence{" "}
                  <span className="not-italic text-lg tracking-[0.2em] uppercase font-normal text-muted-foreground/80" style={{ fontFamily: "\"Manrope\", sans-serif" }}>
                    Think deeper. Work smarter.
                  </span>
                </p>
              </div>
            </div>

            <div className="space-y-12 max-w-md mx-auto pt-4 w-full">
              <button
                onClick={() => void handleSignIn()}
                disabled={isSigningIn}
                className="group relative w-full flex items-center justify-center gap-4 bg-card border border-primary/25 text-foreground px-8 py-5 rounded-xl hover:bg-primary/5 hover:border-primary/40 transition-all shadow-lg hover:shadow-xl duration-300 transform hover:-translate-y-0.5 disabled:opacity-60 disabled:pointer-events-none"
              >
                {isSigningIn ? <Loader2 className="h-7 w-7 animate-spin" /> : <GoogleIcon />}
                <span className="font-semibold text-xl tracking-tight" style={{ fontFamily: "\"Manrope\", sans-serif" }}>
                  {isSigningIn ? "Signing in..." : "Sign in with Google"}
                </span>
                <div className="absolute inset-0 rounded-xl ring-2 ring-primary/25 opacity-0 group-hover:opacity-100 group-hover:scale-105 transition-all duration-300 pointer-events-none" />
              </button>

              {auth.lastError && (
                <p className="text-sm text-destructive text-center -mt-8" style={{ fontFamily: "\"Manrope\", sans-serif" }}>
                  {auth.lastError}
                </p>
              )}

              <div className="relative pt-6">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-border to-transparent" />
                <div className="flex flex-col items-center mt-6">
                  <p
                    className="text-sm md:text-base font-bold tracking-[0.15em] text-foreground/80 uppercase"
                    style={{ fontFamily: "\"Manrope\", sans-serif" }}
                  >
                    DESIGNED &amp; DEVELOPED BY Pravin Gadekar
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      <StatusFooter />
    </div>
  )
}
