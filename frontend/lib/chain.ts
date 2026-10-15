import { createAccount, createClient } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { ExecutionResult, type TransactionHash, TransactionHashVariant, TransactionStatus } from 'genlayer-js/types';
export const CHAIN_ID = 61999;
export const CHAIN_HEX = '0xf22f';
export const RPC_URL = 'https://studio.genlayer.com/api';
export const EXPLORER = 'https://explorer-studio.genlayer.com';
export const REGISTRY = process.env.NEXT_PUBLIC_REGISTRY_ADDRESS || '';
export const MARKET = process.env.NEXT_PUBLIC_MARKET_ADDRESS || '';
export type TxPhase = 'IDLE' | 'ESTIMATING' | 'AWAITING_SIGNATURE' | 'SUBMITTED' | 'DECIDED' | 'FINALIZED' | 'FAILED';
export type TxRecord = { hash: string; method: string; phase: TxPhase; error?: string; created: number };
export type BrowserProvider = { request(args: { method: string; params?: unknown[] | object }): Promise<unknown>; on?: (event:string, cb: (...args: any[]) => void) => void; removeListener?: (event:string, cb: (...args:any[])=>void) => void };
declare global { interface Window { ethereum?: BrowserProvider } }
let selectedProvider: BrowserProvider | undefined;
async function injectedProvider(): Promise<BrowserProvider> {
  if (selectedProvider) return selectedProvider;
  const announced: BrowserProvider[] = [];
  const receive = (event: Event) => {
    const provider = (event as CustomEvent<{provider?: BrowserProvider}>).detail?.provider;
    if (provider && !announced.includes(provider)) announced.push(provider);
  };
  window.addEventListener('eip6963:announceProvider', receive);
  window.dispatchEvent(new Event('eip6963:requestProvider'));
  await new Promise(resolve => setTimeout(resolve, 100));
  window.removeEventListener('eip6963:announceProvider', receive);
  selectedProvider = announced[0] || window.ethereum;
  if (!selectedProvider) throw new Error('An injected EIP-1193 wallet is required. WalletConnect and Snaps are not supported.');
  return selectedProvider;
}
export function shorten(value:string, head=7, tail=5) { return value.length>head+tail+3 ? `${value.slice(0,head)}…${value.slice(-tail)}` : value; }
export function validAddress(x:string) { return /^0x[a-f0-9]{40}$/i.test(x); }
export function validTx(x:string) { return /^0x[a-f0-9]{64}$/i.test(x); }
export function validSha(x:string) { return /^[0-9a-f]{64}$/.test(x); }
export function validPinned(x:string) { return /^https:\/\/raw\.githubusercontent\.com\/[^/?#]+\/[^/?#]+\/[0-9a-f]{40}\/.+/.test(x); }
export function genToWei(value:string) { if (!/^\d+(\.\d{1,18})?$/.test(value)) throw new Error('Enter a positive GEN amount with up to 18 decimals'); const [a,b='']=value.split('.'); return BigInt(a)*10n**18n+BigInt((b+'0'.repeat(18)).slice(0,18)); }
export function formatGen(value: string | number | bigint) { const n=BigInt(value); const fraction=(n%10n**18n).toString().padStart(18,'0').slice(0,4); return `${n/10n**18n}.${fraction} GEN`; }
export function readClient() { return createClient({ chain:studionet, account:createAccount() }); }
export async function readContract<T=unknown>(address:string, method:string, args:unknown[]=[]) {
  if (!validAddress(address)) throw new Error('Contract not deployed: configure frontend/.env.local');
  const result = await readClient().readContract({ address:address as `0x${string}`, functionName:method, args:args as any[], transactionHashVariant:TransactionHashVariant.LATEST_FINAL });
  return result as T;
}
export async function connectWallet() {
  const provider = await injectedProvider();
  const accounts = (await provider.request({method:'eth_requestAccounts'})) as string[];
  if (!accounts?.[0] || !validAddress(accounts[0])) throw new Error('No wallet account selected');
  const chain = (await provider.request({method:'eth_chainId'})) as string;
  return { address: accounts[0], chainId: parseInt(chain,16), provider };
}
export async function switchToStudionet() {
  const provider = await injectedProvider();
  try { await provider.request({method:'wallet_switchEthereumChain',params:[{chainId:CHAIN_HEX}]}); }
  catch (error:any) {
    if (error?.code !== 4902 && error?.code !== -32603) throw error;
    await provider.request({method:'wallet_addEthereumChain',params:[{
      chainId:CHAIN_HEX,chainName:'GenLayer Studionet',nativeCurrency:{name:'GEN',symbol:'GEN',decimals:18},
      rpcUrls:[RPC_URL],blockExplorerUrls:[EXPLORER]
    }]});
  }
  const now = String(await provider.request({method:'eth_chainId'}));
  if (parseInt(now,16)!==CHAIN_ID) throw new Error('Wallet remains on wrong network');
}
export type ContractWrite = { address:string; method:string; args:unknown[]; value?:bigint };
export async function writeContract(wallet:string, write:ContractWrite, report:(phase:TxPhase,hash?:string,error?:string)=>void):Promise<string> {
  const provider = await injectedProvider();
  const current = Number.parseInt(String(await provider.request({method:'eth_chainId'})),16);
  if (current!==CHAIN_ID) throw new Error('Wrong network: switch to Studionet 61999 before signing');
  const accounts = (await provider.request({method:'eth_accounts'})) as string[];
  const selected = accounts?.[0];
  if (!selected || !validAddress(selected)) throw new Error('The injected wallet is disconnected');
  if (selected.toLowerCase() !== wallet.toLowerCase()) {
    throw new Error('The selected wallet account changed. Review the form and try again.');
  }
  if (!validAddress(write.address)) throw new Error('Target contract not deployed');
  const client = createClient({ chain:studionet, account:wallet as `0x${string}`, provider:provider as any });
  await client.connect('studionet');
  const request={address:write.address as `0x${string}`,functionName:write.method,args:write.args as any[],value:write.value??0n};
  report('AWAITING_SIGNATURE');
  const hash=await client.writeContract(request);
  report('SUBMITTED',hash);
  // The write is never automatically resubmitted once we have a transaction hash.
  try {
    const decision=await client.waitForTransactionReceipt({hash,status:TransactionStatus.ACCEPTED});
    if (decision.txExecutionResultName === ExecutionResult.FINISHED_WITH_ERROR) {report('FAILED',hash,`Decision ${decision.statusName} / ${decision.txExecutionResultName}`);return hash;}
    report('DECIDED',hash);
    const final=await client.waitForTransactionReceipt({hash,status:TransactionStatus.FINALIZED});
    if (final.txExecutionResultName !== ExecutionResult.FINISHED_WITH_RETURN) {report('FAILED',hash,`Finalization ${final.statusName} / ${final.txExecutionResultName}`);return hash;}
    report('FINALIZED',hash);
  } catch(e:any) {
    // An RPC timeout after hash issuance is not proof of failure. Preserve hash for recovery.
    report('SUBMITTED',hash,`Tracking interrupted: ${String(e?.message||e)}. Inspect tx before retrying.`);
  }
  return hash;
}

/** Inspect an existing transaction by hash without repeating the underlying write. */
export async function recoverTransaction(hash:string):Promise<{phase:TxPhase;error?:string}> {
  if (!validTx(hash)) throw new Error('Invalid submitted transaction hash');
  const receipt=await readClient().waitForTransactionReceipt({hash:hash as TransactionHash,status:TransactionStatus.FINALIZED});
  return receipt.txExecutionResultName === ExecutionResult.FINISHED_WITH_RETURN
    ? {phase:'FINALIZED'}
    : {phase:'FAILED',error:`Finalized with ${receipt.statusName} / ${receipt.txExecutionResultName}`};
}
