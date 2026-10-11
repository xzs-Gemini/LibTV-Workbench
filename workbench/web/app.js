const $=s=>document.querySelector(s);
const states={queued:'等待中',creating:'创建云端任务',ready:'准备生成',running:'生成中',downloading:'下载中',complete:'已完成',needs_review:'需要核对',checking:'核对中',cancelled:'已取消',failed:'未完成'};
let models=[],schema={},jobsSignature='',modelEpoch=0;
function notice(message){$('#notice').textContent=message;$('#notice').hidden=!message}
async function api(path,body){const res=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await res.json();if(!res.ok)throw Error(data.error||'请求失败');return data}
function option(value,text){const o=document.createElement('option');o.value=value;o.textContent=text;return o}
async function loadModels(){const epoch=++modelEpoch;$('#submit').disabled=true;$('#model').replaceChildren();try{const result=await api('/api/models?kind='+$('#kind').value);if(epoch!==modelEpoch)return;models=result;for(const model of models)$('#model').append(option(model.modelName,model.modelName));if($('#kind').value==='image'&&models.some(m=>m.modelName==='Z-image Turbo'))$('#model').value='Z-image Turbo';await loadSchema(epoch)}catch(e){notice(e.message)}}
async function loadSchema(epoch=modelEpoch){
  $('#submit').disabled=true;
  $('#settings').replaceChildren();
  const selected=$('#model').value;
  try{
    const result=await api('/api/schema?name='+encodeURIComponent(selected));
    if(epoch!==modelEpoch||selected!==$('#model').value)return;
    schema=result;
    $('#schema').textContent=JSON.stringify(schema.schema,null,2);
    $('#model-note').textContent=models.find(m=>m.modelName===selected)?.description||'';
    for(const [key,property] of Object.entries(schema.schema?.properties||{})){
      if(!property||!['ratio','quality','duration','count','resolution'].includes(key))continue;
      const values=Array.isArray(property)?property:property.enum;
      let control;
      if(Array.isArray(values)&&values.length){
        control=document.createElement('select');
        const choices=values.map(item=>typeof item==='object'?{value:item.value,label:item.displayName??item.label??String(item.value)}:{value:item,label:String(item)}).filter(item=>item.value!==undefined);
        for(const item of choices)control.append(option(JSON.stringify(item.value),item.label));
        control.value=JSON.stringify(property.default??choices[0]?.value);
        if(control.selectedIndex<0)control.selectedIndex=0;
      }else if(typeof property.min==='number'&&typeof property.max==='number'){
        control=document.createElement('input');control.type='number';
        control.min=property.min;control.max=property.max;control.step=property.step??1;
        control.value=property.default??property.min;control.required=true;
      }else continue;
      const wrap=document.createElement('div'),label=document.createElement('label');
      control.id='param-'+key;control.dataset.param=key;label.htmlFor=control.id;
      label.textContent=property.displayName||({count:'每条生成数量',ratio:'比例',duration:'时长（秒）'}[key]||key);
      wrap.append(label,control);$('#settings').append(wrap);
    }
    $('#submit').disabled=!selected;
  }catch(e){notice(e.message)}
}
function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node}
async function action(path,id,button){button.disabled=true;try{await api(path,{id});notice('');await refresh()}catch(e){notice(e.message);button.disabled=false}}
function render(jobs){$('#count').textContent=jobs.length;$('#waiting').textContent=jobs.filter(j=>j.status==='queued').length;$('#active').textContent=jobs.filter(j=>['creating','ready','running','downloading','checking'].includes(j.status)).length;$('#done').textContent=jobs.filter(j=>j.status==='complete').length;const signature=JSON.stringify(jobs);if(signature===jobsSignature)return;jobsSignature=signature;$('#jobs').replaceChildren();if(!jobs.length){const empty=el('div',undefined,'empty');empty.append(el('strong','第一批素材，从这里开始'),el('span','左侧写下需求，生成结果会自动出现在这里。'));$('#jobs').append(empty)}for(const job of jobs){const card=el('article',undefined,'job');const head=el('div',undefined,'job-head');head.append(el('span',job.model+' · '+new Date(job.created*1000).toLocaleString('zh-CN')),el('span',states[job.status]||job.status,'status'));card.append(head,el('p',job.prompt));if(['running','downloading'].includes(job.status)){const progress=el('progress');progress.max=100;if(job.progress>0)progress.value=job.progress;progress.setAttribute('aria-label','生成进度');card.append(progress)}if(job.error)card.append(el('div',job.error,'error'));const files=el('div',undefined,'files');for(const file of job.files){const url='/outputs/'+job.id+'/'+encodeURIComponent(file),link=el('a');link.href=url;link.download=file;if(/\.(png|jpe?g|webp)$/i.test(file)){const img=el('img');img.src=url;img.alt=job.prompt;img.loading='lazy';link.append(img)}link.append(el('span','下载 '+file));files.append(link)}card.append(files);const actions=el('div',undefined,'job-actions');if(job.status==='queued'){const btn=el('button','取消排队');btn.onclick=()=>action('/api/cancel',job.id,btn);actions.append(btn)}if(['needs_review','failed','complete'].includes(job.status)){const btn=el('button',job.status==='complete'?'重新下载':'核对云端状态');btn.onclick=()=>action('/api/check',job.id,btn);actions.append(btn)}card.append(actions);$('#jobs').append(card)}}
async function refresh(){try{const state=await api('/api/state');render(state.jobs);$('#paused').hidden=!state.paused;$('#connection').textContent='● 本地服务已连接';if($('#notice').textContent==='本地服务连接中断，请重新启动工作台')notice('')}catch(e){$('#connection').textContent='本地服务连接中断';notice('本地服务连接中断，请重新启动工作台')}}
$('#form').onsubmit=async event=>{event.preventDefault();const button=$('#submit');button.disabled=true;try{const params=JSON.parse($('#advanced').value||'{}');if(!params||typeof params!=='object'||Array.isArray(params))throw Error('高级参数应为 JSON 对象');for(const select of document.querySelectorAll('[data-param]'))params[select.dataset.param]=JSON.parse(select.value);await api('/api/jobs',{project:$('#project').value,kind:$('#kind').value,model:$('#model').value,prompts:$('#prompts').value.split('\n').map(p=>p.trim()).filter(Boolean),params});notice('');$('#prompts').value='';await refresh()}catch(e){notice(e.message)}finally{button.disabled=false}};
$('#kind').onchange=loadModels;$('#model').onchange=()=>loadSchema();$('#refresh').onclick=refresh;document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{$('#prompts').value+=($('#prompts').value?'\n':'')+b.dataset.prompt;$('#prompts').focus()});
(async()=>{try{const [projects,state]=await Promise.all([api('/api/projects'),api('/api/state')]);for(const project of projects)$('#project').append(option(project.id,project.name));if(projects.some(p=>p.id===state.defaultProject))$('#project').value=state.defaultProject;render(state.jobs);await loadModels();await refresh()}catch(e){notice(e.message)}setInterval(refresh,4000)})();

$('#resume').onclick=async()=>{try{await api('/api/resume',{});await refresh()}catch(e){notice(e.message)}};
