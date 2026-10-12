"use client"
import { useEffect, useMemo, useRef, useState } from "react"
import { ReactFlow, Background, Controls, MiniMap, Position, MarkerType, addEdge, reconnectEdge, useNodesState, useEdgesState, type Node, type Edge, type Connection } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { Button } from "@/components/ui/button"
import { FlowStepSettings } from "./flow-step-settings"
interface Def { nodes?: any[]; edges?: any[] }
export const STEP_TYPES: Record<string,string> = { trigger:"Trigger", agent_invoke:"Ask an agent", http_request:"Internal service request", notification:"Notify organisation owners", transform:"Set values", condition:"Condition", end:"End" }
function flowNode(n:any,i=0):Node { return { id:n.id, type:n.type==="trigger"?"input":n.type==="end"?"output":"default", position:n.config?.position || {x:50+i*240,y:100}, sourcePosition:Position.Right,targetPosition:Position.Left,
  data:{label:`${n.name||n.id}\n${STEP_TYPES[n.type]||n.type}`,node:n},style:{whiteSpace:"pre-line",fontSize:12,border:`2px solid ${n.type==="trigger"?"#f59e0b":n.type==="end"?"#10b981":"#7c5cff"}`,borderRadius:12,padding:12,width:190} } }
function toFlow(def:Def) { return { nodes:(def.nodes||[]).map(flowNode),edges:(def.edges||[]).map((e,i):Edge=>({id:`${e.from}-${e.to}-${i}`,source:e.from,target:e.to,label:e.condition,type:"smoothstep",markerEnd:{type:MarkerType.ArrowClosed},interactionWidth:24})) } }
function toDef(nodes:Node[],edges:Edge[]):Def { return { nodes:nodes.map(n=>({...n.data.node as any,id:n.id,config:{...(n.data.node as any).config,position:n.position}})),edges:edges.map(e=>({from:e.source,to:e.target,...(e.label?{condition:String(e.label)}:{})})) } }
export function FlowCanvas({definition,onChange}:{definition:Def;onChange:(d:Def)=>void}) {
  const initial=useMemo(()=>toFlow(definition),[]) // Parent remounts on workflow, AI proposal and raw JSON replacement.
  const [nodes,setNodes,onNodesChange]=useNodesState(initial.nodes),[edges,setEdges,onEdgesChange]=useEdgesState(initial.edges)
  const [addType,setAddType]=useState("agent_invoke"),[selection,setSelection]=useState<{node?:string;edge?:string}>({}),[error,setError]=useState("")
  const [history,setHistory]=useState<Def[]>([toDef(initial.nodes,initial.edges)]),[index,setIndex]=useState(0)
  const last=useRef(JSON.stringify(history[0])),restoring=useRef(false),reconnected=useRef(false),emit=useRef(onChange);emit.current=onChange
  useEffect(()=>{ const next=toDef(nodes,edges),serialized=JSON.stringify(next); if(serialized===last.current)return;last.current=serialized;emit.current(next)
    if(restoring.current){restoring.current=false;return}setHistory(old=>[...old.slice(0,index+1),next].slice(-40));setIndex(old=>Math.min(old+1,39))
  },[nodes,edges])
  function travel(i:number){if(!history[i])return;restoring.current=true;const next=toFlow(history[i]);setNodes(next.nodes);setEdges(next.edges);setIndex(i);setSelection({})}
  const selected=nodes.find(n=>n.id===selection.node),edge=edges.find(e=>e.id===selection.edge)
  function remove(){const ids=new Set(nodes.filter(n=>n.selected||n.id===selection.node).map(n=>n.id));setNodes(old=>old.filter(n=>!ids.has(n.id)));setEdges(old=>old.filter(e=>!e.selected&&e.id!==selection.edge&&!ids.has(e.source)&&!ids.has(e.target)));setSelection({})}
  function valid(c:Connection|Edge,ignore?:string){ if(!c.source||!c.target||c.source===c.target)return false
    const source:any=nodes.find(n=>n.id===c.source)?.data.node,target:any=nodes.find(n=>n.id===c.target)?.data.node,others=edges.filter(e=>e.id!==ignore)
    if(!source||!target||source.type==="end"||target.type==="trigger"||others.some(e=>e.source===c.source&&e.target===c.target)||others.filter(e=>e.source===c.source).length>=(source.type==="condition"?2:1))return false
    const reaches=(id:string,seen=new Set<string>()):boolean=>{if(id===c.source)return true;if(seen.has(id))return false;seen.add(id);return others.filter(e=>e.source===id).some(e=>reaches(e.target,seen))};return !reaches(c.target)
  }
  function add(){if(addType==="trigger"&&nodes.some(n=>(n.data.node as any).type==="trigger")){setError("A workflow has one trigger. Select it to configure it.");return}
    const id=`${addType}_${crypto.randomUUID().slice(0,8)}`,config=addType==="agent_invoke"?{agent_type:"assistant",message:"{{input.message}}",draft_only:true}:addType==="notification"?{title:"Workflow update",body:"{{input.message}}"}:addType==="condition"?{left:"{{input.value}}",op:"eq",right:""}:addType==="http_request"?{service:"sales",path:"/",method:"GET"}:{}
    setNodes(old=>[...old.map(n=>({...n,selected:false})),{...flowNode({id,type:addType,name:STEP_TYPES[addType],config},nodes.length),selected:true}]);setSelection({node:id});setError("")
  }
  function update(patch:any){if(!selected)return;const original:any=selected.data.node;setNodes(old=>old.map(n=>n.id===selected.id?{...flowNode({...original,...patch}),position:n.position,selected:true}:n))}
  return <div className="space-y-3">
    <div className="flex flex-wrap gap-2 items-center"><select aria-label="Step type to add" value={addType} onChange={e=>setAddType(e.target.value)} className="rounded border bg-background p-2 text-sm">{Object.entries(STEP_TYPES).map(([type,label])=><option key={type} value={type}>{label}</option>)}</select><Button size="sm" variant="outline" onClick={add}>+ Add step</Button>
      <Button size="sm" variant="outline" disabled={!selected&&!edge&&!nodes.some(n=>n.selected)&&!edges.some(e=>e.selected)} onClick={remove}>Delete selected</Button><Button size="sm" variant="ghost" disabled={!index} onClick={()=>travel(index-1)}>Undo</Button><Button size="sm" variant="ghost" disabled={index>=history.length-1} onClick={()=>travel(index+1)}>Redo</Button><Button size="sm" variant="ghost" onClick={()=>setNodes(old=>old.map((n,i)=>({...n,position:{x:50+i*240,y:100}})))}>Arrange</Button></div>
    {error&&<p role="alert" className="text-sm text-destructive">{error}</p>}<p className="text-xs text-muted-foreground">Click a step to edit. Click a connection to disconnect. Drag handles to connect or reconnect. Delete / Backspace removes selections; Shift selects more than one.</p>
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_290px]"><div className="h-[480px] min-w-0 rounded-xl border bg-background" tabIndex={0} aria-label="Workflow graph">
      <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={c=>{if(!valid(c)){setError("Loops, duplicates and parallel paths are not supported. A condition can have two branches.");return}const source:any=nodes.find(n=>n.id===c.source)?.data.node;setEdges(old=>addEdge({...c,type:"smoothstep",markerEnd:{type:MarkerType.ArrowClosed},label:source?.type==="condition"?(edges.some(e=>e.source===c.source&&e.label==="true")?"false":"true"):undefined},old));setError("")}}
        onNodesDelete={deleted=>{const ids=new Set(deleted.map(n=>n.id));setEdges(old=>old.filter(e=>!ids.has(e.source)&&!ids.has(e.target)));setSelection({})}} onNodeClick={(_,n)=>setSelection({node:n.id})} onEdgeClick={(_,e)=>setSelection({edge:e.id})} onPaneClick={()=>setSelection({})}
        edgesReconnectable onReconnectStart={()=>{reconnected.current=false}} onReconnect={(old,c)=>{if(valid(c,old.id)){reconnected.current=true;setEdges(all=>reconnectEdge(old,c,all))}}} onReconnectEnd={(_,old)=>{if(!reconnected.current)setEdges(all=>all.filter(e=>e.id!==old.id))}}
        deleteKeyCode={["Backspace","Delete"]} multiSelectionKeyCode="Shift" fitView colorMode="dark" minZoom={0.2} maxZoom={2} snapToGrid snapGrid={[20,20]}><Background/><Controls/><MiniMap pannable zoomable nodeColor="#7c5cff"/></ReactFlow>
    </div><aside className="rounded-xl border bg-card p-4 min-w-0 space-y-3" aria-label="Step and connection settings">
      {!selected&&!edge&&<><h3 className="font-semibold">Step settings</h3><p className="text-sm text-muted-foreground">Choose a step or connection. Configure the workflow event or schedule above.</p></>}
      {selected&&<FlowStepSettings key={selected.id} node={selected.data.node as any} onChange={update} onDelete={remove} onError={setError} onDuplicate={()=>{const original:any=selected.data.node,id=`${original.type}_${crypto.randomUUID().slice(0,8)}`;setNodes(old=>[...old.map(n=>({...n,selected:false})),{...flowNode({...original,id,name:`${original.name} copy`,config:{...original.config,position:{x:selected.position.x+40,y:selected.position.y+100}}}),selected:true}]);setSelection({node:id})}}/>}
      {edge&&<><h3 className="font-semibold">Connection</h3><p className="text-sm break-all">{edge.source} → {edge.target}</p>{(nodes.find(n=>n.id===edge.source)?.data.node as any)?.type==="condition"&&<label className="block text-sm">Branch<select className="block w-full rounded border bg-background p-2" value={String(edge.label||"true")} onChange={e=>setEdges(old=>old.map(item=>item.id===edge.id?{...item,label:e.target.value}:item))}><option>true</option><option>false</option></select></label>}<Button size="sm" variant="destructive" onClick={()=>{setEdges(old=>old.filter(item=>item.id!==edge.id));setSelection({})}}>Disconnect</Button></>}
    </aside></div>
  </div>
}
