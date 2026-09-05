"use client"

/**
 * FlowCanvas — drag-drop React-Flow editor for a workflow definition.
 * Converts between our definition ({nodes:[{id,type,name,config}], edges:[{from,to}]})
 * and React Flow's node/edge shape, and emits the updated definition on change.
 * Node positions are persisted in node.config.position so layouts survive save.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { Button } from "@/components/ui/button"

interface Def {
  nodes?: any[]
  edges?: any[]
}

const NODE_TYPES = ["trigger", "agent_invoke", "http_request", "transform", "condition", "end"]

function toFlow(def: Def): { nodes: Node[]; edges: Edge[] } {
  const nodes = (def.nodes ?? []).map((n, i) => ({
    id: n.id,
    position: n.config?.position ?? { x: 60 + i * 200, y: 80 + (i % 2) * 40 },
    data: { label: `${n.name || n.id}\n(${n.type})`, node: n },
    style: { whiteSpace: "pre-line", fontSize: 12, border: "1px solid #7c5cff", borderRadius: 8, padding: 8 },
  })) as Node[]
  const edges = (def.edges ?? []).map((e) => ({
    id: `${e.from}-${e.to}`, source: e.from, target: e.to,
    label: e.condition, animated: true,
  })) as Edge[]
  return { nodes, edges }
}

function toDef(nodes: Node[], edges: Edge[]): Def {
  return {
    nodes: nodes.map((n) => {
      const orig = (n.data as any)?.node ?? { id: n.id, type: "transform", name: n.id, config: {} }
      return { ...orig, id: n.id, config: { ...(orig.config ?? {}), position: n.position } }
    }),
    edges: edges.map((e) => ({ from: e.source, to: e.target, ...(e.label ? { condition: String(e.label) } : {}) })),
  }
}

export function FlowCanvas({ definition, onChange }: { definition: Def; onChange: (d: Def) => void }) {
  const initial = useMemo(() => toFlow(definition), []) // eslint-disable-line react-hooks/exhaustive-deps
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges)
  const [addType, setAddType] = useState("agent_invoke")
  const emit = useRef(onChange)
  emit.current = onChange

  // Push changes up whenever the graph changes.
  useEffect(() => {
    emit.current(toDef(nodes, edges))
  }, [nodes, edges])

  const onConnect = useCallback((c: Connection) => setEdges((eds) => addEdge({ ...c, animated: true }, eds)), [setEdges])

  const addNode = useCallback(() => {
    const id = `${addType}_${Math.random().toString(36).slice(2, 6)}`
    const node: Node = {
      id,
      position: { x: 120 + Math.random() * 240, y: 120 + Math.random() * 160 },
      data: { label: `${id}\n(${addType})`, node: { id, type: addType, name: id, config: {} } },
      style: { whiteSpace: "pre-line", fontSize: 12, border: "1px solid #7c5cff", borderRadius: 8, padding: 8 },
    }
    setNodes((ns) => [...ns, node])
  }, [addType, setNodes])

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <select value={addType} onChange={(e) => setAddType(e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1 text-xs">
          {NODE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <Button size="sm" variant="outline" onClick={addNode}>+ Add node</Button>
        <span className="text-xs text-muted-foreground">Drag to move · drag between handles to connect · edit config in the JSON below</span>
      </div>
      <div style={{ height: 340 }} className="rounded-lg border border-border">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          colorMode="dark"
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  )
}
