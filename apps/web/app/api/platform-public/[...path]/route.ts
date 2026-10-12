import {NextRequest,NextResponse} from "next/server"
const upstream=process.env.ADMIN_SERVICE_URL||"http://admin:8013"
async function handle(request:NextRequest,context:{params:Promise<{path:string[]}>}){
  const {path}=await context.params
  const action=path.join("/")
  if(!((request.method==="GET"&&action==="demo")||(request.method==="POST"&&["trial-request","demo/book","demo/manage","demo/request"].includes(action))))return new NextResponse(null,{status:404})
  try{
    const body=request.method==="POST"?await request.text():undefined
    if(body&&body.length>4000)return new NextResponse(null,{status:413})
    const headers:Record<string,string>={"Content-Type":"application/json"}
    const peer=request.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim()
    if(peer)headers["x-forwarded-for"]=peer
    const query=action==="demo"&&request.nextUrl.searchParams.has("day")?`?day=${encodeURIComponent(request.nextUrl.searchParams.get("day")!)}`:""
    const result=await fetch(`${upstream}/public/platform/${action}${query}`,{method:request.method,headers,body,cache:"no-store",signal:AbortSignal.timeout(15000)})
    return new NextResponse(await result.text(),{status:result.status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}})
  }catch{return NextResponse.json({detail:"OmniDome onboarding is unavailable. Please try again."},{status:503})}
}
export const GET=handle
export const POST=handle
