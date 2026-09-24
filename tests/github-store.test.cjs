const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {GitHubStore}=require('../src/foundry/service/static/github-store.js');
const catalog=require('../src/foundry/service/static/catalog.json');
class GitServer {
 constructor(){this.blobs=new Map();this.trees=new Map();this.commits=new Map();this.head=null;this.counter=0;this.writes=0;this.conflict=null;this.deny=false;this.uncertain=false;}
 id(){return (++this.counter).toString(16).padStart(40,'0');}
 json(data,status=200){return new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}});}
 putBlob(bytes){const sha=this.id();this.blobs.set(sha,Buffer.from(bytes));return sha;}
 async fetch(url,options){
  assert.ok(url.startsWith('https://api.github.com/'));
  assert.equal(options.headers.Authorization,'Bearer test-token');
  const path=url.replace('https://api.github.com','').replace('/repos/owner/repo','');
  const method=options.method,body=options.body?JSON.parse(options.body):null;
  if(method!=='GET')this.writes++;
  if(path==='/user')return this.json({login:'alice'});
  if(path==='')return this.json({private:false,permissions:{push:true}});
  if(path==='/git/ref/heads/foundry-data')return this.head?this.json({object:{sha:this.head}}):this.json({},404);
  if(path.startsWith('/git/commits/')&&method==='GET')return this.json(this.commits.get(path.split('/').pop()));
  if(path.startsWith('/git/trees/')&&method==='GET')return this.json({tree:this.trees.get(path.split('/').pop()),truncated:false});
  if(path.startsWith('/git/blobs/')&&method==='GET'){const b=this.blobs.get(path.split('/').pop());return this.json({content:b.toString('base64'),size:b.length});}
  if(path==='/git/blobs'&&method==='POST')return this.json({sha:this.putBlob(Buffer.from(body.content,'base64'))},201);
  if(path==='/git/trees'&&method==='POST'){
   let entries=[...(this.trees.get(body.base_tree)||[])];
   for(const entry of body.tree){const sha=entry.sha||this.putBlob(Buffer.from(entry.content));entries=entries.filter(e=>e.path!==entry.path);entries.push({...entry,sha});}
   const sha=this.id();this.trees.set(sha,entries);return this.json({sha},201);
  }
  if(path==='/git/commits'&&method==='POST'){const sha=this.id();this.commits.set(sha,{tree:{sha:body.tree},parents:body.parents});return this.json({sha},201);}
  if(path==='/git/refs'&&method==='POST'){if(this.head)return this.json({},422);this.head=body.sha;return this.json({object:{sha:this.head}},201);}
  if(path==='/git/refs/heads/foundry-data'&&method==='PATCH'){
   assert.equal(body.force,false);if(this.deny)return this.json({},403);
   if(this.conflict){const action=this.conflict;this.conflict=null;action();}
   if(this.commits.get(body.sha).parents[0]!==this.head)return this.json({},422);
   this.head=body.sha;
   if(this.uncertain){this.uncertain=false;throw new Error('network response lost');}
   return this.json({object:{sha:this.head}});
  }
  throw new Error('Unhandled mock route '+method+' '+path);
 }
 state(){const entries=this.trees.get(this.commits.get(this.head).tree.sha);return JSON.parse(this.blobs.get(entries.find(e=>e.path==='index.json').sha));}
 externalSample(){const state=this.state();state.samples.push({id:'LOT-BOB',kind:'lot',parent_id:null,created_by:'bob'});const entries=[...this.trees.get(this.commits.get(this.head).tree.sha)].filter(e=>e.path!=='index.json');entries.push({path:'index.json',type:'blob',sha:this.putBlob(Buffer.from(JSON.stringify(state)))});const tree=this.id();this.trees.set(tree,entries);const head=this.id();this.commits.set(head,{tree:{sha:tree},parents:[this.head]});this.head=head;}
}
async function setup(){const server=new GitServer(),client=new GitHubStore({repository:'owner/repo',token:'test-token',catalog,fetcher:server.fetch.bind(server)});await client.connect();return {server,client};}
async function sample(client){await client.addSample({id:'LOT-001',kind:'lot',parent_id:null});await client.addSample({id:'WAF-001',kind:'wafer',parent_id:'LOT-001'});}
const record=()=>({submission_id:'test-submit-001',sample_id:'WAF-001',process_type:'annealing',occurred_at:'2026-01-01T10:00:00+08:00',equipment_id:null,recipe:null,notes:'test',supersedes_id:null,parameters:{temperature:{value:400,unit:'°C'},duration:{value:30,unit:'min'}}});

test('login only reads, never initializes or uploads data',async()=>{const {server,client}=await setup();assert.equal(server.writes,0);assert.equal(client.visibility,'public');});
test('default browser fetch keeps the global receiver during login',async(t)=>{
 const server=new GitServer();
 t.mock.method(globalThis,'fetch',function(url,options){
  assert.equal(this,globalThis,'browser fetch requires the Window receiver');
  return server.fetch(url,options);
 });
 const client=new GitHubStore({repository:'owner/repo',token:'test-token',catalog});
 assert.deepEqual(await client.connect(),{name:'alice',role:'editor',visibility:'public'});
 assert.equal(server.writes,0);
});
test('sample and record normalization, idempotency, and immutable files',async()=>{const {server,client}=await setup();await sample(client);const first=await client.addRecord(record());assert.equal(first.parameters.temperature.value,673.15);assert.equal(first.parameters.duration.value,1800);assert.equal((await client.addRecord(record())).id,first.id);assert.equal(server.state().records.length,1);assert.equal(first.author,'alice');const data=record();data.notes='different';await assert.rejects(client.addRecord(data),/相同提交编号/);});
test('concurrent writer is preserved without force-push',async()=>{const {server,client}=await setup();await sample(client);server.conflict=()=>server.externalSample();await client.addRecord(record());assert.ok(server.state().samples.some(s=>s.id==='LOT-BOB'));assert.equal(server.state().records.length,1);});
test('uncertain successful response can be retried without duplication',async()=>{const {server,client}=await setup();await sample(client);server.uncertain=true;await assert.rejects(client.addRecord(record()),/response lost/);await client.addRecord(record());assert.equal(server.state().records.length,1);});
test('branch protection failure does not publish a partial index',async()=>{const {server,client}=await setup();await sample(client);server.deny=true;await assert.rejects(client.addRecord(record()),/拒绝访问/);assert.equal(server.state().records.length,0);});
test('attachment bytes, unicode filename, deduplication, and correction lineage',async()=>{const {server,client}=await setup();await sample(client);const first=await client.addRecord(record());const bytes=Uint8Array.from([0,255,1,65,0,128]);const file=new File([bytes],'气体日志.zip');const saved=await client.upload(first.id,file);assert.equal((await client.upload(first.id,file)).id,saved.id);assert.deepEqual(new Uint8Array(await (await client.download(saved.id)).arrayBuffer()),bytes);const correction={...record(),submission_id:'new-version-001',supersedes_id:first.id};const second=await client.addRecord(correction);assert.equal((await client.listAttachments(second.id)).length,1);const rows=await client.api('/api/records?include_history=false');assert.equal(rows.total,1);assert.equal(rows.items[0].id,second.id);});
test('invalid units, hierarchy, empty and oversized files rejected before blob writes',async()=>{const {server,client}=await setup();await assert.rejects(client.addSample({id:'DEV',kind:'device',parent_id:null}),/父级/);await sample(client);const data=record();data.parameters.duration.unit='W';await assert.rejects(client.addRecord(data),/参数或单位/);const first=await client.addRecord(record());const before=server.writes;await assert.rejects(client.upload(first.id,{size:51*1024*1024,name:'big.zip'}),/50 MiB/);await assert.rejects(client.upload(first.id,new File([],'empty.zip')),/不能为空/);assert.equal(server.writes,before);});
test('download corruption is detected',async()=>{const {server,client}=await setup();await sample(client);const first=await client.addRecord(record());const a=await client.upload(first.id,new File(['data'],'test.log'));server.blobs.set(a.blob_sha,Buffer.from('oops'));await assert.rejects(client.download(a.id),/校验失败/);});
test('repository and branch cannot redirect credentials to another host',()=>{assert.throws(()=>new GitHubStore({repository:'https://evil.example',token:'secret',catalog}),/仓库应/);assert.throws(()=>new GitHubStore({repository:'a/b',branch:'../../x',token:'secret',catalog}),/数据分支/);});
