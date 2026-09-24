"use strict";
const $ = id => document.getElementById(id);
let token = "", catalog, samples = [], account, offset = 0, total = 0, correction = null;
const newId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2,"0")).join("");
let githubStore=null;
let submissionId = newId();
let attachmentRecord = null;
function message(text, error=false) { $("message").textContent=text; $("message").className=error?"error":""; }
async function api(path, method="GET", body) {
  if(githubStore)return githubStore.api(path,method,body);
  const res=await fetch(path,{method, headers:{Authorization:"Bearer "+token,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
  const data=await res.json();
  if (!res.ok) { const detail=Array.isArray(data.detail)?data.detail.map(x=>x.loc.join(".")+": "+x.msg).join("\n"):data.detail; throw new Error(detail||"请求失败"); }
  return data;
}
function option(value,label){const item=document.createElement("option");item.value=value;item.textContent=label;return item;}
function fillSamples(){
  const selected=$("sample").value, filter=$("filterSample").value;
  $("sample").replaceChildren(option("","请选择已登记样品"));$("filterSample").replaceChildren(option("","全部样品"));
  samples.forEach(s=>{$("sample").append(option(s.id,s.id));$("filterSample").append(option(s.id,s.id));});
  $("sample").value=selected;$("filterSample").value=filter;fillParents();$("summary").textContent=`已登记 ${samples.length} 个样品 / 批次`;
}
function fillParents(){const kind=$("sampleKind").value, expected={wafer:"lot",die:"wafer",device:"die"}[kind];$("parent").replaceChildren(option("",kind==="lot"?"无（批次）":"请选择父级"));samples.filter(s=>s.kind===expected).forEach(s=>$("parent").append(option(s.id,s.id)));$("parent").disabled=kind==="lot";$("parent").required=kind!=="lot";}
function parameterRow(name="duration", quantity=null){
  const row=document.createElement("div");row.className="parameter-row";
  const key=document.createElement("select"), value=document.createElement("input"), unit=document.createElement("select"), remove=document.createElement("button");
  Object.entries(catalog.parameters).forEach(([k,s])=>key.append(option(k,s.label)));key.value=name;
  value.type="number";value.step="any";value.placeholder="未填写";
  function units(){unit.replaceChildren(...Object.keys(catalog.parameters[key.value].units).map(u=>option(u,u)));}
  units();key.addEventListener("change",()=>{value.value="";units();});
  if(quantity){value.value=quantity.value;unit.value=quantity.unit;}
  for(const [label,node] of [["参数",key],["数值",value],["单位",unit]]){const wrap=document.createElement("label");wrap.textContent=label;wrap.append(node);row.append(wrap);}
  remove.type="button";remove.textContent="×";remove.className="secondary";remove.setAttribute("aria-label","移除参数");remove.onclick=()=>row.remove();row.append(remove);
  row.getQuantity=()=>({name:key.value, value:value.value, unit:unit.value});$("parameters").append(row);
}
function defaultParameters(){ $("process").dataset.previous=$("process").value; $("parameters").replaceChildren();catalog.process_types[$("process").value].defaults.forEach(p=>parameterRow(p)); }
function reset(){ $("recordForm").reset();correction=null;submissionId=newId();$("entryMode").textContent="新记录";defaultParameters(); }
function startCorrection(record){
  $("newAttachments").value="";
  correction=record.id;submissionId=newId();$("sample").value=record.sample_id;$("process").value=record.process_type;$("process").dataset.previous=record.process_type;
  const date=new Date(record.occurred_at);const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);$("occurred").value=local.toISOString().slice(0,16);
  $("equipment").value=record.equipment_id||"";$("recipe").value=record.recipe||"";$("notes").value=record.notes;
  $("parameters").replaceChildren();Object.entries(record.original_parameters).forEach(([name,q])=>parameterRow(name,q));
  $("entryMode").textContent="更正已有记录";$("entryCard").scrollIntoView({behavior:"smooth"});message("更正后将新增版本，保留原记录。请填写更正原因。");
}
async function loadRecords(){
  const query=new URLSearchParams({limit:"25",offset:String(offset),include_history:String($("history").checked)});
  if($("filterSample").value)query.set("sample_id",$("filterSample").value);if($("filterProcess").value)query.set("process_type",$("filterProcess").value);
  const data=await api("/api/records?"+query);total=data.total;$("records").replaceChildren();
  data.items.forEach(r=>{
    const tr=document.createElement("tr");const values=[new Date(r.occurred_at).toLocaleString(),r.sample_id+"\n"+catalog.process_types[r.process_type].label,Object.entries(r.parameters).map(([k,q])=>`${catalog.parameters[k]?.label||k}: ${Number(q.value.toPrecision(9))} ${q.unit}`).join("\n"),(r.equipment_id||"设备未填写")+"\n"+r.author];
    values.forEach(value=>{const td=document.createElement("td");td.textContent=value;tr.append(td);});
    const td=document.createElement("td"), details=document.createElement("details"), summary=document.createElement("summary"), p=document.createElement("p");summary.textContent="查看原始信息";p.textContent=`记录：${r.id}\n配方：${r.recipe||"未填写"}\n原时间：${r.original_occurred_at}\n录入时间：${new Date(r.created_at).toLocaleString()}\n原参数：${Object.entries(r.original_parameters).map(([k,q])=>`${catalog.parameters[k]?.label||k} ${q.value} ${q.unit}`).join("；")}\n备注：${r.notes||"无"}\n更正来源：${r.supersedes_id||"无"}`;details.append(summary,p);td.append(details);
    if(account.role==="editor"){const button=document.createElement("button");button.className="secondary small";button.textContent="更正";button.onclick=()=>startCorrection(r);td.append(button);}const attachButton=document.createElement("button");attachButton.className="secondary small";attachButton.textContent="附件";attachButton.onclick=()=>openAttachments(r).catch(e=>message(e.message,true));td.append(attachButton);tr.append(td);$("records").append(tr);
  });
  if(!data.items.length){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=5;td.textContent="暂无记录。登记样品后，从上方表单开始录入。";const attachButton=document.createElement("button");attachButton.className="secondary small";attachButton.textContent="附件";attachButton.onclick=()=>openAttachments(r).catch(e=>message(e.message,true));td.append(attachButton);tr.append(td);$("records").append(tr);}
  $("recordCount").textContent=`共 ${total} 条记录，按工艺开始时间倒序排列`;
  $("page").textContent=`第 ${Math.floor(offset/25)+1} 页`;$("prev").disabled=offset===0;$("next").disabled=offset+25>=total;
}
$("loginForm").addEventListener("submit",async e=>{e.preventDefault();token=$("token").value.trim();try{
  if($("storageMode").value==="github"){
    const catalogResponse=await fetch(new URL("catalog.json",document.querySelector('script[src$="github-store.js"]').src));if(!catalogResponse.ok)throw new Error("参数目录加载失败");
    githubStore=new GitHubStore({repository:$("githubRepo").value.trim(),branch:$("githubBranch").value.trim(),token,catalog:await catalogResponse.json()});
    await githubStore.connect();
    $("storageNotice").textContent=`GitHub：${githubStore.repository} / ${githubStore.branch}。${githubStore.visibility==="public"?"这是公开仓库，上传的参数和附件对所有人可见。":"这是私有仓库，仅获授权的仓库成员可访问。"}`;
    if(githubStore.visibility==="public"&&!confirm("此仓库是公开的，之后上传的工艺记录和附件将公开可见。仅上传允许公开的数据。是否连接？")){githubStore=null;token="";return;}
  }else{githubStore=null;$("storageNotice").textContent="本机数据库：数据保存在运行服务的电脑上。";}
  account=await api("/api/me");catalog=await api("/api/catalog");samples=await api("/api/samples");$("process").replaceChildren();$("filterProcess").replaceChildren(option("","全部工艺"));Object.entries(catalog.process_types).forEach(([k,s])=>{$("process").append(option(k,s.label));$("filterProcess").append(option(k,s.label));});fillSamples();defaultParameters();offset=0;await loadRecords();$("workspace").hidden=false;$("loginBox").hidden=true;$("entryCard").hidden=account.role!=="editor";$("sampleCard").hidden=account.role!=="editor";$("identity").textContent=account.name+" · "+(account.role==="editor"?"可录入":"只读");$("token").value="";message("已连接，共享记录已加载。");}catch(err){token="";githubStore=null;message(err.message,true);}});
$("logout").onclick=()=>{token="";location.reload();};
$("sampleKind").onchange=fillParents;
$("sampleForm").addEventListener("submit",async e=>{e.preventDefault();try{const id=$("sampleId").value.trim();await api("/api/samples","POST",{id,kind:$("sampleKind").value,parent_id:$("parent").value||null});samples=await api("/api/samples");fillSamples();$("sample").value=id;$("sampleId").value="";message("样品登记成功："+id);}catch(err){message(err.message,true);}});
$("process").onchange=()=>{if(Array.from($("parameters").children).some(r=>r.getQuantity().value!=="")&&!confirm("切换工艺类型会清空当前参数，是否继续？")){$("process").value=$("process").dataset.previous||"etching";return;}defaultParameters();$("process").dataset.previous=$("process").value;};
$("addParameter").onclick=()=>parameterRow();$("newRecord").onclick=()=>{if(confirm("清空当前表单，开始新记录？")){reset();message("");}};
$("recordForm").addEventListener("submit",async e=>{
  e.preventDefault();$("save").disabled=true;
  try{const parameters={};for(const row of $("parameters").children){const q=row.getQuantity();if(q.value==="")continue;if(q.name in parameters)throw new Error("同一参数不能重复填写；多阶段工艺请分开记录。");parameters[q.name]={value:Number(q.value),unit:q.unit};}
    if(!Object.keys(parameters).length)throw new Error("请至少填写一个参数。");
    const data={submission_id:submissionId,sample_id:$("sample").value,process_type:$("process").value,occurred_at:new Date($("occurred").value).toISOString(),equipment_id:$("equipment").value.trim()||null,recipe:$("recipe").value.trim()||null,parameters,notes:$("notes").value,supersedes_id:correction};
    const selected=Array.from($("newAttachments").files);
    validateFiles(selected);
    const saved=await api("/api/records","POST",data);
    // The record is committed independently. Never create a second record to retry files.
    reset();offset=0;$("filterSample").value="";$("filterProcess").value="";
    let uploadError="";
    if(selected.length){try{await sendFiles(saved.id,selected);}catch(err){uploadError=err.message;}}
    try{await loadRecords();if(selected.length)await openAttachments(saved);}catch(err){message("记录已保存："+saved.id+"。刷新失败，请稍后刷新。"+(uploadError?" 附件："+uploadError:""),true);return;}
    message("记录已保存："+saved.id+(uploadError?"。附件未全部上传："+uploadError+"。请在下方附件区补传，无需重新创建工艺记录。":selected.length?"。附件上传完成。":"。已按样品和工艺类型归档。"),Boolean(uploadError));
  }catch(err){message(err.message,true);}finally{$("save").disabled=false;}
});
for(const id of ["filterSample","filterProcess","history"])$(id).onchange=()=>{offset=0;loadRecords().catch(e=>message(e.message,true));};
$("refresh").onclick=async()=>{try{samples=await api("/api/samples");fillSamples();await loadRecords();}catch(e){message(e.message,true);}};
$("prev").onclick=()=>{offset=Math.max(0,offset-25);loadRecords().catch(e=>message(e.message,true));};$("next").onclick=()=>{offset+=25;loadRecords().catch(e=>message(e.message,true));};

function validateFiles(files){for(const file of files){if(!file.size)throw new Error(file.name+" 是空文件");if(file.size>50*1024*1024)throw new Error(file.name+" 超过50 MiB");}}
async function sendFiles(recordId,files){
  validateFiles(files);
  for(let i=0;i<files.length;i++){
    const file=files[i];$("attachmentStatus").textContent=`上传 ${i+1}/${files.length}：${file.name}`;
    if(githubStore){await githubStore.upload(recordId,file);continue;}
    const res=await fetch(`/api/records/${encodeURIComponent(recordId)}/attachments?filename=${encodeURIComponent(file.name)}`,{method:"POST",headers:{Authorization:"Bearer "+token,"Content-Type":"application/octet-stream"},body:file});
    if(!res.ok){const data=await res.json();throw new Error(file.name+"："+(typeof data.detail==="string"?data.detail:"上传失败"));}
  }
}
async function openAttachments(record){
  attachmentRecord=record;$("attachmentCard").hidden=false;$("attachmentTarget").textContent=`${record.sample_id} · ${catalog.process_types[record.process_type].label} · ${record.id}`;
  $("attachmentUploadArea").hidden=account.role!=="editor";$("attachmentFiles").value="";$("attachmentStatus").textContent="正在加载附件…";
  await refreshAttachments();$("attachmentCard").scrollIntoView({behavior:"smooth"});
}
async function refreshAttachments(){
  const items=await api(`/api/records/${encodeURIComponent(attachmentRecord.id)}/attachments`);$("attachmentList").replaceChildren();
  $("attachmentStatus").textContent=items.length?`共 ${items.length} 个附件（含更正前版本）`:"此工艺还没有附件。";
  for(const item of items){
    const row=document.createElement("div");row.className="attachment-item";
    const info=document.createElement("div"),title=document.createElement("strong"),detail=document.createElement("p");
    title.textContent=item.filename;detail.className="hint";detail.textContent=`${(item.size/1024/1024).toFixed(2)} MiB · ${item.uploaded_by} · ${new Date(item.uploaded_at).toLocaleString()}${item.record_id!==attachmentRecord.id?" · 来自更正前版本":""}\nSHA-256: ${item.sha256}`;info.append(title,detail);
    const download=document.createElement("button");download.type="button";download.className="secondary small";download.textContent="下载";download.setAttribute("aria-label","下载 "+item.filename);
    download.onclick=async()=>{download.disabled=true;try{let fileBlob;if(githubStore){fileBlob=await githubStore.download(item.id);}else{const res=await fetch(`/api/attachments/${encodeURIComponent(item.id)}/download`,{headers:{Authorization:"Bearer "+token}});if(!res.ok)throw new Error("下载失败，请检查登录状态");fileBlob=await res.blob();}const url=URL.createObjectURL(fileBlob);const a=document.createElement("a");a.href=url;a.download=item.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(err){$("attachmentStatus").textContent=err.message;}finally{download.disabled=false;}};
    row.append(info,download);$("attachmentList").append(row);
  }
}
$("closeAttachments").onclick=()=>{$("attachmentCard").hidden=true;};
$("uploadAttachments").onclick=async()=>{
  const files=Array.from($("attachmentFiles").files);if(!files.length){$("attachmentStatus").textContent="请先选择文件。";return;}
  $("uploadAttachments").disabled=true;
  try{await sendFiles(attachmentRecord.id,files);$("attachmentFiles").value="";await refreshAttachments();}
  catch(err){try{await refreshAttachments();}catch(_){}$("attachmentStatus").textContent=err.message+"；已上传成功的附件已保留，可重试（相同文件不会重复保存）。";}
  finally{$("uploadAttachments").disabled=false;}
};

$("storageMode").onchange=()=>{$("githubSettings").hidden=$("storageMode").value!=="github";$("token").value="";};
if(location.protocol!=="file:"&&!['127.0.0.1','localhost','::1'].includes(location.hostname)){$("storageMode").value="github";$("storageMode").querySelector('option[value="local"]').disabled=true;$("storageMode").onchange();}
