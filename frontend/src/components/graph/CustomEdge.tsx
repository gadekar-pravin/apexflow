import { memo } from "react"
import { BaseEdge, getSmoothStepPath, type EdgeProps } from "@xyflow/react"

function CustomEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  animated,
}: EdgeProps) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  })

  const filterId = `edge-glow-${id}`

  return (
    <>
      {/* Glow layer for animated edges */}
      {animated && (
        <BaseEdge
          id={`${id}-glow`}
          path={edgePath}
          style={{
            stroke: "hsl(var(--foreground) / 0.15)",
            strokeWidth: 6,
            strokeLinecap: "round",
            filter: "blur(4px)",
          }}
        />
      )}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: animated ? "hsl(var(--foreground) / 0.4)" : "hsl(var(--border))",
          strokeWidth: 1.5,
          strokeLinecap: "round",
          ...style,
        }}
        className={animated ? "animate-pulse-subtle" : undefined}
      />
      {/* Flowing dot on animated edges */}
      {animated && (
        <>
          <defs>
            <filter id={filterId} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <circle
            r="3"
            fill="hsl(var(--foreground) / 0.6)"
            filter={`url(#${filterId})`}
            className="edge-flow-dot"
          >
            <animateMotion
              dur="2s"
              repeatCount="indefinite"
              path={edgePath}
            />
          </circle>
        </>
      )}
    </>
  )
}

export const CustomEdge = memo(CustomEdgeComponent)
