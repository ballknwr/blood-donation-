'use strict';
const $ = id => document.getElementById(id);
const groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
let csrf = '', user = null, registering = false, activeMatch = null;
let knownNotifications = new Set(), notifiedAccount = null;
const escapeHtml = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function flash(message, error=false) { $('flash').textContent=message; $('flash').className='flash'+(error?' error':''); $('flash').hidden=false; }
async function api(path, method='GET', body) {
  const response=await fetch('/api/'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok) throw new Error(result.error || 'Something went wrong. Try again.');
  return result;
}
function formData(form) {const d=Object.fromEntries(new FormData(form)); form.querySelectorAll('input[type=checkbox]').forEach(el=>d[el.name]=el.checked); return d;}
function locationData() {return {lat:Number($('lat').value),lon:Number($('lon').value)};}
async function refreshSession() {
  const result=await api('session'); csrf=result.csrf; user=result.user;
  $('account-button').textContent=user?'Sign out':'Sign in';
  $('account-status').textContent=user?`Signed in as ${user.name}. WhatsApp: ${result.whatsapp_mode}. ${result.donor?'Donor profile saved · '+(result.donor.available?'available':'unavailable'): 'No donor profile yet.'}`:'Sign in to see your requests and donor inbox.';
  if(result.donor) {
    const f=$('donor-form'); f.elements.blood_group.value=result.donor.blood_group;
    f.elements.available.checked=Boolean(result.donor.available); f.elements.whatsapp_consent.checked=Boolean(result.donor.whatsapp_consent);
  }
}
function requireUser(){if(user)return true; $('auth-dialog').showModal(); return false;}
async function searchCentres(){
  const d=locationData(); const result=await api(`centres?lat=${encodeURIComponent(d.lat)}&lon=${encodeURIComponent(d.lon)}`);
  $('centres').innerHTML=result.centres.slice(0,3).map(c=>`<article class="centre-card"><div class="centre-icon">✚</div><h3>${escapeHtml(c.name)}</h3><p>${escapeHtml(c.city)} · Fictional demonstration location</p><div class="centre-bottom"><strong>↗ ${c.distance_km} km away</strong><span class="sample">SAMPLE ONLY</span></div></article>`).join('');
}
async function refreshDashboard(){
  if(!user){ for(const id of ['requests','inbox','notifications']) $(id).innerHTML='<p class="empty">Sign in to view this section.</p>'; $('unread').textContent='0 new';return; }
  const d=await api('dashboard');
  $('requests').innerHTML=d.requests.map(r=>`<article class="request-card"><div class="card-heading"><span class="blood-badge">${escapeHtml(r.blood_group)}</span><span class="state">${r.status}</span></div><strong>#${r.id} · ${escapeHtml(r.hospital)}</strong><p>${escapeHtml(r.city)} · ${r.units} unit(s)</p>${r.matches.length?r.matches.map(m=>`<p>${escapeHtml(m.name)} · ${m.distance} km · <strong>${escapeHtml(m.status)}</strong></p>`).join(''):'<p>No available same-group volunteers within 50 km yet. Contact your hospital; alerts are not a guarantee of help.</p>'}${r.matches.some(m=>m.status==='accepted')?'<p class="form-note">A volunteer is willing to attend. The donor should approach the named hospital/blood centre with this request ID. Staff must verify the request and arrange screening; this app does not book an appointment or share contact details.</p>':''}${r.status==='open'?`<button class="secondary small" data-close-request="${r.id}">Close request</button>`:''}</article>`).join('') || '<p class="empty">No requests yet. Post one above.</p>';
  $('inbox').innerHTML=d.inbox.map(m=>`<article class="inbox-card"><div class="card-heading"><span class="blood-badge">${escapeHtml(m.blood_group)}</span><span class="state">${m.request_status==='closed'?'request closed':escapeHtml(m.status)}</span></div><strong>Request #${m.request_id} · ${escapeHtml(m.hospital)}</strong><p>${escapeHtml(m.city)} · ${m.distance} km · ${m.units} unit(s)</p><p class="form-note">WhatsApp: ${escapeHtml(m.whatsapp_status)}. ${m.whatsapp_status==='dry-run'?'No external message sent.':''}</p>${m.status==='pending'&&m.request_status==='open'?`<div class="card-actions"><button data-accept="${m.id}">Review & accept</button><button class="secondary" data-decline="${m.id}">Decline</button></div>`:m.status==='accepted'?'<p class="form-note">Your willingness is recorded. Contact the named hospital/blood centre through its official channels and quote the request ID. Do not travel until staff confirm arrangements.</p>':''}</article>`).join('') || '<p class="empty">No matched requests yet. Save your donor profile to receive future requests.</p>';
  $('notifications').innerHTML=d.notifications.map(n=>`<article class="note ${n.read?'':'unread'}"><div>${escapeHtml(n.message)}</div><small>${escapeHtml(new Date(n.created_at).toLocaleString())}</small></article>`).join('') || '<p class="empty">You’re all caught up.</p>';
  $('unread').textContent=d.notifications.filter(n=>!n.read).length+' new';
  if(notifiedAccount===user.id && 'Notification' in window && Notification.permission==='granted') {
    d.notifications.filter(n=>!n.read&&!knownNotifications.has(n.id)).forEach(()=>{new Notification('RakhtConnect',{body:'You have a new update. Open your connection desk to review it.',tag:'rakht-update'});});
  }
  notifiedAccount=user.id;knownNotifications=new Set(d.notifications.map(n=>n.id));
}
function handle(task){return async event=>{event?.preventDefault();try{await task(event);}catch(e){flash(e.message,true);}};}
document.querySelectorAll('.groups').forEach(select=>{select.innerHTML=groups.map(g=>`<option>${g}</option>`).join('');});
document.querySelectorAll('input[type=date]').forEach(input=>{const d=new Date();input.max=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;});
$('location').addEventListener('change',handle(async()=>{if($('location').value==='custom')return;[$('lat').value,$('lon').value]=$('location').value.split(','); const city=$('location').selectedOptions[0].textContent.split(',')[0]; $('request-form').elements.city.value=city; $('donor-form').elements.city.value=city; await searchCentres();}));
$('search').addEventListener('click',handle(searchCentres));
$('locate').addEventListener('click',()=>{if(!navigator.geolocation){flash('Geolocation is unavailable. Enter coordinates manually.',true);return;} navigator.geolocation.getCurrentPosition(p=>{ $('lat').value=p.coords.latitude; $('lon').value=p.coords.longitude; $('location').value='custom'; searchCentres().catch(e=>flash(e.message,true));},()=>flash('Location was unavailable or denied. Choose a city or enter coordinates.',true),{timeout:10000});});
$('account-button').addEventListener('click',handle(async()=>{if(!user){$('auth-dialog').showModal();return;} await api('logout','POST',{});await refreshSession();await refreshDashboard();flash('Signed out.');}));
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>$(b.dataset.close).close()));
$('toggle-auth').addEventListener('click',()=>{registering=!registering;$('name-label').hidden=!registering;$('auth-form').elements.name.required=registering;$('auth-title').textContent=registering?'Join the community.':'Good to see you.';$('auth-submit').textContent=registering?'Create account':'Sign in';$('toggle-auth').textContent=registering?'Already registered? Sign in':'New here? Create an account';$('auth-form').elements.password.autocomplete=registering?'new-password':'current-password';$('auth-error').textContent='';});
$('auth-form').addEventListener('submit',async e=>{e.preventDefault();const button=$('auth-submit');button.disabled=true;try{await api(registering?'register':'login','POST',formData(e.target));await refreshSession();await refreshDashboard();$('auth-dialog').close();e.target.reset();flash('Signed in. You can now post a request or save a donor profile.');}catch(error){$('auth-error').textContent=error.message;}finally{button.disabled=false;}});
for(const [id,path,success] of [['request-form','requests','Request posted.'],['donor-form','donor','Donor profile saved. Only future requests are matched; update availability here to opt out.']]){
  $(id).addEventListener('submit',handle(async e=>{if(!requireUser())return;const button=e.target.querySelector('[type=submit]');button.disabled=true;try{const result=await api(path,'POST',{...formData(e.target),...locationData()});await refreshSession();await refreshDashboard();flash(success+(path==='requests'?` ${result.matched} volunteer(s) notified in the app. No donor is guaranteed.`:''));}finally{button.disabled=false;}}));
}
$('dashboard').addEventListener('click',handle(async e=>{const b=e.target.closest('button');if(!b)return;
 if(b.dataset.accept){activeMatch=b.dataset.accept;$('screen-form').reset();$('screen-error').textContent='';$('screen-dialog').showModal();}
 if(b.dataset.decline){await api(`matches/${b.dataset.decline}/respond`,'POST',{action:'decline'});await refreshDashboard();flash('Request declined.');}
 if(b.dataset.closeRequest){await api(`requests/${b.dataset.closeRequest}/close`,'POST',{});await refreshDashboard();flash('Request closed.');}
}));
$('screen-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('[type=submit]');button.disabled=true;try{await api(`matches/${activeMatch}/respond`,'POST',{...formData(e.target),action:'accept'});$('screen-dialog').close();await refreshDashboard();flash('Willingness recorded. Contact the named hospital through its official channels and confirm arrangements before travelling. Clinical screening is still required.');}catch(error){$('screen-error').textContent=error.message;}finally{button.disabled=false;}});
$('refresh').addEventListener('click',handle(async()=>{await refreshSession();await refreshDashboard();}));
$('mark-read').addEventListener('click',handle(async()=>{if(!requireUser())return;await api('notifications/read','POST',{});await refreshDashboard();}));
$('enable-notifications').addEventListener('click',handle(async()=>{if(!('Notification' in window)){flash('Browser notifications are unavailable. Use the in-app inbox.',true);return;}const permission=await Notification.requestPermission();flash(permission==='granted'?'Browser alerts enabled while this page is open.':'Browser alerts are blocked. In-app notifications still work.',permission!=='granted');}));
(async()=>{try{await refreshSession();await searchCentres();await refreshDashboard();}catch(e){flash(e.message,true);}})();
setInterval(()=>{if(user&&!document.hidden)refreshDashboard().catch(()=>{});},15000);
