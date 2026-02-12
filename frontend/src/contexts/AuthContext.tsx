import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { getApp, getApps, initializeApp, type FirebaseApp } from "firebase/app"
import {
  getAuth,
  getRedirectResult,
  GoogleAuthProvider,
  onIdTokenChanged,
  signInWithRedirect,
  signOut as firebaseSignOut,
  type Auth,
  type User,
} from "firebase/auth"
import { setAuthTokenProvider } from "@/services/api"

interface AuthContextValue {
  isConfigured: boolean
  isInitializing: boolean
  isAuthenticated: boolean
  user: User | null
  lastError: string | null
  signIn: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const FIREBASE_HOSTING_DOMAINS: ReadonlySet<string> = new Set([
  "askcortex.dev",
  "apexflow-console.web.app",
])

function resolveAuthDomain(): string | undefined {
  const hostname = window.location.hostname
  if (FIREBASE_HOSTING_DOMAINS.has(hostname)) {
    return hostname
  }
  return import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined
}

function getFirebaseConfig() {
  const config = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
    authDomain: resolveAuthDomain(),
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET as string | undefined,
    messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID as string | undefined,
    appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
  }

  const required = [config.apiKey, config.authDomain, config.projectId, config.appId]
  const isConfigured = required.every((value) => Boolean(value))

  return { config, isConfigured }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const { config, isConfigured } = useMemo(getFirebaseConfig, [])
  const [isInitializing, setIsInitializing] = useState(isConfigured)
  const [user, setUser] = useState<User | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const authRef = useRef<Auth | null>(null)
  const lastUidRef = useRef<string | null>(null)
  const isFirstFireRef = useRef(true)

  useEffect(() => {
    if (!isConfigured) {
      setAuthTokenProvider(() => Promise.resolve(null))
      setIsInitializing(false)
      return
    }

    try {
      const app: FirebaseApp = getApps().length > 0 ? getApp() : initializeApp(config)
      const auth = getAuth(app)
      authRef.current = auth

      setAuthTokenProvider(async () => {
        const currentUser = auth.currentUser
        return currentUser ? currentUser.getIdToken() : null
      })

      // Handle redirect result (catches errors from signInWithRedirect flow)
      getRedirectResult(auth).catch((error) => {
        const message = error instanceof Error ? error.message : "Sign-in redirect failed"
        setLastError(message)
      })

      const unsubscribe = onIdTokenChanged(auth, (nextUser) => {
        setUser(nextUser)
        setLastError(null)
        setIsInitializing(false)

        const nextUid = nextUser?.uid ?? null
        if (isFirstFireRef.current) {
          isFirstFireRef.current = false
          lastUidRef.current = nextUid
        } else if (lastUidRef.current !== nextUid) {
          lastUidRef.current = nextUid
          queryClient.clear()
        }
      })

      return () => unsubscribe()
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to initialize Firebase Auth"
      setLastError(message)
      setIsInitializing(false)
      setAuthTokenProvider(() => Promise.resolve(null))
      return
    }
  }, [config, isConfigured, queryClient])

  const signIn = useCallback(async () => {
    if (!authRef.current) return

    try {
      setLastError(null)
      const provider = new GoogleAuthProvider()
      provider.setCustomParameters({ prompt: "select_account" })
      await signInWithRedirect(authRef.current, provider)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Sign-in failed"
      setLastError(message)
    }
  }, [])

  const signOut = useCallback(async () => {
    if (!authRef.current) return

    try {
      setLastError(null)
      await firebaseSignOut(authRef.current)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Sign-out failed"
      setLastError(message)
    }
  }, [])

  const value: AuthContextValue = {
    isConfigured,
    isInitializing,
    isAuthenticated: Boolean(user),
    user,
    lastError,
    signIn,
    signOut,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
