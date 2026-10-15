import { NextRequest,NextResponse } from 'next/server';
import { createHash } from 'node:crypto';
import { validAddress,validPinned,validSha,validTx } from '../../../lib/chain';
export const runtime='nodejs';
const RPC='https://studio.genlayer.com/api';
function digest(x:Uint8Array){return createHash('sha256').update(x).digest('hex')}
async function rpc(method:string,params:unknown[]){
  const response=await fetch(RPC,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',method,id:1,params}),cache:'no-store',signal:AbortSignal.timeout(22000)});
  if (!response.ok)throw new Error(`${method} failed with HTTP ${response.status}`);
  const doc=await response.json();if(doc.error||doc.result===undefined)throw new Error(`${method}: ${JSON.stringify(doc.error||'result missing').slice(0,160)}`);
  return doc.result;
}
async function pinned(url:string){
  const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(18000)});
  if(!response.ok)throw new Error(`Pinned source unavailable (${response.status})`);
  const bytes=new Uint8Array(await response.arrayBuffer());if(bytes.length===0||bytes.length>100000)throw new Error('Pinned source empty or oversized');return bytes;
}
export async function POST(request:NextRequest){
  try{
    const body=await request.json();
    const {target,txHash,sourceUrl,sourceSha256}=body;
    if(!validAddress(target)||!validTx(txHash)||!validPinned(sourceUrl)||!validSha(sourceSha256))return NextResponse.json({error:'Invalid pinned suite or transaction values'},{status:400});
    const [source,code,receipt]=await Promise.all([
      pinned(sourceUrl),rpc('gen_getContractCode',[target]),
      rpc('eth_getTransactionByHash',[txHash])]);
    if(typeof code!=='string')throw new Error('Deployed code unavailable');
    const actual=new Uint8Array(Buffer.from(code,'base64'));
    const observations={
      chainId:61999,sourcePinned:digest(source)===sourceSha256,
      deployedMatchesPinned:digest(actual)===digest(source),
      deployedSourceSha256:digest(actual),sourceSha256:digest(source),
      finalized:String(receipt?.status||'').toUpperCase()==='FINALIZED',
      receiptTargetMatches:String(receipt?.to_address||'').toLowerCase()===target.toLowerCase(),
      receiptHashMatches:String(receipt?.hash||'').toLowerCase()===txHash.toLowerCase(),
      consensusAgreed:Number(receipt?.result)===6,
      execution:JSON.stringify(receipt?.consensus_data?.leader_receipt?.[0]||{}).slice(0,10000)
    };
    const base=observations.sourcePinned&&observations.deployedMatchesPinned&&observations.finalized&&observations.receiptTargetMatches&&observations.receiptHashMatches&&observations.consensusAgreed;
    return NextResponse.json({status:base?'READY_FOR_SEMANTIC_REVIEW':'EVIDENCE_BLOCKED',observations,
      note:'This check verifies provenance and finality. It is NOT a GenLayer consensus verdict, bug confirmation or bounty authorization.'});
  }catch(e:any){return NextResponse.json({error:`Evidence verification unavailable: ${String(e?.message||e)}`},{status:503})}
}
