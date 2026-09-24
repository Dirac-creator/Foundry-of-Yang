/* GitHub-backed storage. Credentials live only in the page instance. */
(function (root) {
"use strict";
const enc = new TextEncoder(), dec = new TextDecoder();
const empty = () => ({schema_version:"1.0.0",samples:[],records:[],attachments:[]});
const assert = (ok,msg) => { if(!ok)throw new Error(msg); };
const base64 = bytes => { let s="";for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s); };
const unbase64 = text => Uint8Array.from(atob(text.replace(/\s/g,"")), c=>c.charCodeAt(0));
const sha256 = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),x=>x.toString(16).padStart(2,"0")).join("");
const stable = value => value && typeof value==="object" ? Array.isArray(value)?value.map(stable):Object.fromEntries(Object.keys(value).sort().map(k=>[k,stable(value[k])])) : value;
const copy = value => JSON.parse(JSON.stringify(value));
class GitHubStore {
  // Native browser fetch must keep Window as its receiver when stored on this instance.
  constructor({repository,branch="foundry-data",token,catalog,fetcher=root.fetch.bind(root)}) {
    assert(/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository),"仓库应填写 所有者/仓库名");
    assert(/^[A-Za-z0-9_-]{1,80}$/.test(branch),"数据分支只支持字母、数字、下划线和短横线");
    this.repository=repository;this.branch=branch;this.token=token;this.catalog=catalog;this.fetcher=fetcher;
    this.base="/repos/"+repository;this.cache=null;this.cacheHead=null;
  }
  async request(path,method="GET",body) {
    // API host cannot be supplied by repository data or a returned download_url.
    const response=await this.fetcher("https://api.github.com"+path,{method,cache:"no-store",headers:{Authorization:"Bearer "+this.token,Accept:"application/vnd.github+json","Content-Type":"application/json","X-GitHub-Api-Version":"2026-03-10"},body:body?JSON.stringify(body):undefined});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){const e=new Error(response.status===401?"GitHub令牌无效或已过期":response.status===403?"GitHub拒绝访问：请检查仓库权限、令牌权限或API限流":response.status===404?"GitHub仓库、分支或文件不存在，或无权访问":response.status===409||response.status===422?"GitHub提交冲突或分支规则阻止写入":`GitHub请求失败 (${response.status})`);e.status=response.status;throw e;}
    return data;
  }
  async connect(){
    const user=await this.request("/user");const repo=await this.request(this.base);
    assert(!repo.archived,"仓库已归档，无法录入");
    this.account={name:user.login,role:repo.permissions?.push===false?"reader":"editor"};
    this.visibility=repo.private?"private":"public";
    await this.snapshot();return {...this.account,visibility:this.visibility};
  }
  async snapshot(){
    let ref;
    try{ref=await this.request(this.base+"/git/ref/heads/"+this.branch);}catch(e){if(e.status===404)return {head:null,tree:null,state:empty()};throw e;}
    const head=ref.object.sha;
    if(this.cacheHead===head && this.cache)return {head,tree:this.cache.tree,state:copy(this.cache.state)};
    const commit=await this.request(this.base+"/git/commits/"+head);
    const tree=await this.request(this.base+"/git/trees/"+commit.tree.sha);
    assert(!tree.truncated,"数据目录过大，无法完整读取，请联系维护者");
    const entry=tree.tree.find(x=>x.path==="index.json"&&x.type==="blob");
    assert(entry,"所选分支不是工艺数据分支。请选择尚不存在的 foundry-data 分支初始化");
    const blob=await this.request(this.base+"/git/blobs/"+entry.sha);
    assert(blob.size<=5*1024*1024,"数据索引超过5 MiB，请先升级存储方案");
    const state=JSON.parse(dec.decode(unbase64(blob.content)));
    assert(state.schema_version==="1.0.0"&&["samples","records","attachments"].every(k=>Array.isArray(state[k])),"不支持的数据索引格式");
    this.cache={tree:commit.tree.sha,state:copy(state)};this.cacheHead=head;
    return {head,tree:commit.tree.sha,state};
  }
  async transact(message,change){
    assert(this.account?.role==="editor","此账号没有仓库写入权限");
    for(let attempt=0;attempt<4;attempt++){
      const snapshot=await this.snapshot();const state=snapshot.state;
      const mutation=await change(state);
      if(mutation.noop)return mutation.result;
      const index=JSON.stringify(state,null,2)+"\n";
      assert(enc.encode(index).length<=5*1024*1024,"数据索引超过5 MiB，未提交");
      const entries=[...(mutation.files||[]),{path:"index.json",mode:"100644",type:"blob",content:index}];
      const tree=await this.request(this.base+"/git/trees","POST",{...(snapshot.tree?{base_tree:snapshot.tree}:{}),tree:entries});
      const commit=await this.request(this.base+"/git/commits","POST",{message,tree:tree.sha,parents:snapshot.head?[snapshot.head]:[]});
      try{
        if(snapshot.head)await this.request(this.base+"/git/refs/heads/"+this.branch,"PATCH",{sha:commit.sha,force:false});
        else await this.request(this.base+"/git/refs","POST",{ref:"refs/heads/"+this.branch,sha:commit.sha});
        this.cache=null;this.cacheHead=null;return mutation.result;
      }catch(error){
        // Never force-push. Retry only if the branch moved (or another writer initialized it).
        if(![409,422].includes(error.status))throw error;
        this.cache=null;this.cacheHead=null;
        let current;try{current=await this.request(this.base+"/git/ref/heads/"+this.branch);}catch(_){throw error;}
        if(current.object.sha===snapshot.head)throw error;
      }
    }
    throw new Error("其他成员正在连续提交。请稍后重试，已保存的数据不会被覆盖。");
  }
  file(path,data){return {path,mode:"100644",type:"blob",content:JSON.stringify(data,null,2)+"\n"};}
  async addSample(data){
    assert(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(data.id),"样品编号无效");
    assert(["lot","wafer","die","device"].includes(data.kind),"样品层级无效");
    return this.transact("登记样品 "+data.id,state=>{
      const previous=state.samples.find(s=>s.id===data.id);
      if(previous){assert(previous.kind===data.kind&&previous.parent_id===data.parent_id,"该样品编号已存在且内容不同");return {noop:true,result:previous};}
      if(data.kind==="lot")assert(data.parent_id===null,"批次不应有父级");
      else assert(state.samples.some(s=>s.id===data.parent_id&&s.kind==={wafer:"lot",die:"wafer",device:"die"}[data.kind]),"父级不存在或层级不正确");
      const saved={...data,created_by:this.account.name,created_at:new Date().toISOString()};state.samples.push(saved);
      return {result:saved,files:[this.file("samples/"+data.id+".json",saved)]};
    });
  }
  async addRecord(data){
    assert(/^[A-Za-z0-9_-]{8,80}$/.test(data.submission_id),"提交编号无效");
    assert(this.catalog.process_types[data.process_type],"工艺类型无效");
    const time=new Date(data.occurred_at);
    assert(/(?:Z|[+-]\d{2}:\d{2})$/i.test(data.occurred_at)&&Number.isFinite(time.getTime())&&time.getTime()<=Date.now(),"请输入带时区的实际工艺时间，不能为未来时间");
    assert(typeof data.notes==="string"&&data.notes.length<=5000,"备注最长5000字符");
    const parameters={};assert(Object.keys(data.parameters).length>0&&Object.keys(data.parameters).length<=30,"请填写1至30个参数");
    for(const [key,q] of Object.entries(data.parameters)){
      const spec=this.catalog.parameters[key], conversion=spec?.units[q.unit];
      assert(conversion&&typeof q.value==="number"&&Number.isFinite(q.value),"参数或单位无效："+key);
      const value=q.value*conversion[0]+conversion[1];assert(Number.isFinite(value)&&value>=0,"参数转换后必须为非负有限数："+key);
      parameters[key]={value,unit:spec.unit};
    }
    // Stable identity handles uncertain network responses, even after another writer advances HEAD.
    const identity=await sha256(enc.encode(this.account.name+":"+data.submission_id));
    const fingerprint=await sha256(enc.encode(JSON.stringify(stable(data))));
    const id="RUN-"+identity.slice(0,32);
    return this.transact("记录工艺 "+id,state=>{
      const old=state.records.find(r=>r.id===id);
      if(old){assert(old.request_hash===fingerprint,"相同提交编号对应不同内容，请开始新记录");return {noop:true,result:old};}
      assert(state.samples.some(s=>s.id===data.sample_id),"请先登记样品");
      if(data.supersedes_id){assert(state.records.some(r=>r.id===data.supersedes_id&&r.sample_id===data.sample_id),"更正必须引用同一样品的记录");assert(!state.records.some(r=>r.supersedes_id===data.supersedes_id),"此记录已被更正，请刷新后更正最新版本");}
      const saved={...data,id,author:this.account.name,created_at:new Date().toISOString(),occurred_at:time.toISOString(),original_occurred_at:data.occurred_at,original_parameters:copy(data.parameters),parameters,capture_version:"1.0.0",request_hash:fingerprint};
      state.records.push(saved);return {result:saved,files:[this.file("records/"+id+".json",saved)]};
    });
  }
  async listAttachments(id){
    const {state}=await this.snapshot(), ids=new Set();let current=id;
    while(current){assert(!ids.has(current),"更正关联存在循环");ids.add(current);const r=state.records.find(r=>r.id===current);assert(r,"工艺记录不存在");current=r.supersedes_id;}
    return state.attachments.filter(a=>ids.has(a.record_id));
  }
  async upload(recordId,file){
    assert(file.size>0&&file.size<=50*1024*1024,"文件不能为空且不能超过50 MiB");
    assert(file.name.length<=240&&!/[\\/\x00-\x1f\x7f]/.test(file.name)&&![".",".."].includes(file.name),"文件名无效");
    const bytes=new Uint8Array(await file.arrayBuffer()),digest=await sha256(bytes);
    const identity=await sha256(enc.encode(recordId+":"+file.name+":"+digest));const id="FILE-"+identity.slice(0,32);
    // Check the record before creating even an unreachable Git blob.
    const initial=await this.snapshot();assert(initial.state.records.some(r=>r.id===recordId),"工艺记录不存在");
    const found=initial.state.attachments.find(a=>a.id===id);if(found)return found;
    assert(this.account.role==="editor","此账号只有查看权限");
    const blob=await this.request(this.base+"/git/blobs","POST",{content:base64(bytes),encoding:"base64"});
    return this.transact("上传工艺附件 "+file.name,state=>{
      const old=state.attachments.find(a=>a.id===id);if(old)return {noop:true,result:old};
      assert(state.records.some(r=>r.id===recordId),"工艺记录不存在");
      const saved={id,record_id:recordId,filename:file.name,size:bytes.length,sha256:digest,uploaded_by:this.account.name,uploaded_at:new Date().toISOString(),blob_sha:blob.sha,path:"attachments/"+recordId+"/"+id+"/"+file.name};
      state.attachments.push(saved);return {result:saved,files:[{path:saved.path,mode:"100644",type:"blob",sha:blob.sha},this.file("attachment-metadata/"+id+".json",saved)]};
    });
  }
  async download(id){
    const {state}=await this.snapshot(),item=state.attachments.find(a=>a.id===id);assert(item,"附件不存在");
    assert(/^[a-f0-9]{40,64}$/.test(item.blob_sha),"附件blob标识无效");
    const blob=await this.request(this.base+"/git/blobs/"+item.blob_sha);const bytes=unbase64(blob.content);
    assert(bytes.length===item.size&&await sha256(bytes)===item.sha256,"附件校验失败，下载内容与记录不一致");
    return new Blob([bytes],{type:"application/octet-stream"});
  }
  async api(path,method="GET",body){
    if(path==="/api/me")return this.account;
    if(path==="/api/catalog")return this.catalog;
    if(path==="/api/samples")return method==="POST"?this.addSample(body):(await this.snapshot()).state.samples;
    if(path==="/api/records"&&method==="POST")return this.addRecord(body);
    const attachment=path.match(/^\/api\/records\/([^/]+)\/attachments$/);if(attachment)return this.listAttachments(decodeURIComponent(attachment[1]));
    if(path.startsWith("/api/records?")){
      const {state}=await this.snapshot(),q=new URLSearchParams(path.split("?")[1]);let rows=state.records;
      if(q.get("include_history")!=="true"){const replaced=new Set(rows.map(r=>r.supersedes_id).filter(Boolean));rows=rows.filter(r=>!replaced.has(r.id));}
      if(q.get("sample_id"))rows=rows.filter(r=>r.sample_id===q.get("sample_id"));if(q.get("process_type"))rows=rows.filter(r=>r.process_type===q.get("process_type"));
      rows.sort((a,b)=>Date.parse(b.occurred_at)-Date.parse(a.occurred_at)||a.id.localeCompare(b.id));const limit=Number(q.get("limit")||50),offset=Number(q.get("offset")||0);
      return {total:rows.length,items:rows.slice(offset,offset+limit),limit,offset};
    }
    throw new Error("GitHub模式不支持此操作");
  }
}
root.GitHubStore=GitHubStore;
if(typeof module!=="undefined")module.exports={GitHubStore,base64,unbase64};
})(globalThis);
