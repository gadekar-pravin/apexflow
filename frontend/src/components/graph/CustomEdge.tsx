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

  return (
    <>
      {/* Glow layer for animated edges */}
      {animated && (
        <BaseEdge
          id={`${id}-glow`}
          path={edgePath}
          style={{
            stroke: "hsl(var(--primary) / 0.3)",
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
          stroke: animated ? "hsl(var(--primary) / 0.6)" : "hsl(var(--border))",
          strokeWidth: 1.5,
          strokeLinecap: "round",
          ...style,
        }}
        className={animated ? "animate-pulse-subtle" : undefined}
      />
    </>
  )
}

export const CustomEdge = memo(CustomEdgeComponent)
