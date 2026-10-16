(() => {
  const s = window.vishnuFirstRun;
  if (!s) return;
  const {$,createChoice,joinChoice,restoreChoice,createForm,firstName,lastName,displayName,bootstrap,
    password,passwordAgain,begin,codes,recovery,saved,privacy,dataPolicy,savePolicy,policyStatus,
    provider,model,apiKey,saveModel,modelStatus,fallback,reviewButton,review,reviewSummary,
    finish,showError} = s;
  createChoice.onclick = () => { createForm.classList.remove('hidden'); firstName.focus(); };
  joinChoice.onclick = () => {
    $('enrollStatus').textContent = 'Connect with a passkey, owner password, or one-time recovery code below.';
    ($('passkeyLogin').disabled ? $('passwordChoice') : $('passkeyLogin'))?.focus();
  };
  restoreChoice.onclick = () => {
    $('troubleOptions').classList.remove('hidden');
    $('passwordForm').classList.add('hidden');
    $('enrollStatus').textContent = 'Enter a saved one-time recovery code to trust this browser with your existing Vishnu. If its runtime was lost, restore the runtime backup first.';
    $('recoveryCode').focus();
  };
  begin.onclick = async () => {
    const first=firstName.value.trim(), secret=bootstrap.value, pass=password.value;
    if(!first)return showError(new Error('Enter your first name.'));
    if(pass.length<12)return showError(new Error('Use an owner password with at least 12 characters.'));
    if(pass!==passwordAgain.value)return showError(new Error('Passwords did not match.'));
    if(secret.length<32)return showError(new Error('Enter the secure runtime setup code.'));
    begin.disabled=true;
    try {
      const result=await api('/first-run/create',{method:'POST',body:JSON.stringify({
        bootstrap_secret:secret,first_name:first,last_name:lastName.value.trim(),
        display_name:displayName.value.trim(),password:pass,
        device_name:(navigator.userAgentData?.platform||navigator.platform||'Web browser')+' browser',
      })});
      bootstrap.value='';password.value='';passwordAgain.value='';
      codes.textContent=(result.recovery_codes||[]).join('\n');
      recovery.classList.remove('hidden');recovery.scrollIntoView({behavior:'smooth',block:'nearest'});
      $('enrollStatus').textContent='Your owner identity and first trusted browser are ready. Save the recovery codes before continuing.';
    } catch(error) { showError(error); } finally { begin.disabled=false; }
  };

  dataPolicy.onchange=()=>{
    s.policySaved=false;
    savePolicy.disabled=false;
    savePolicy.textContent='Save data placement';
    policyStatus.textContent='Changing this default never silently moves data that already exists.';
    review.classList.add('hidden');
  };
  savePolicy.onclick=async()=>{
    savePolicy.disabled=true;
    policyStatus.textContent='Saving data placement…';
    try {
      const result=await api('/data-plane/settings',{method:'PUT',body:JSON.stringify({default_policy:dataPolicy.value})});
      const savedPolicy=result?.settings?.default_policy||dataPolicy.value;
      if(savedPolicy!==dataPolicy.value)throw new Error('Vishnu did not confirm the selected data placement policy.');
      s.policySaved=true;
      savePolicy.textContent='Data placement saved';
      policyStatus.textContent='Saved. This is the default for newly governed data; existing data was not moved.';
      $('enrollStatus').textContent='';
    } catch(error) {
      savePolicy.disabled=false;
      policyStatus.textContent='Data placement was not saved.';
      showError(error);
    }
  };

  provider.onchange=()=>{
    const selected=provider.value,external=!['skip','local'].includes(selected);
    model.classList.toggle('hidden',selected==='skip');apiKey.classList.toggle('hidden',!external);
    model.placeholder=selected==='local'?'Local model (optional)':'Model name (required for provider setup)';
    review.classList.add('hidden');
  };
  saveModel.onclick=async()=>{
    if(!['skip','local'].includes(provider.value)&&!model.value.trim())return showError(new Error('Enter the provider model name.'));
    try {
      await api('/first-run/model',{method:'POST',body:JSON.stringify({provider_id:provider.value,model:model.value.trim(),api_key:apiKey.value})});
      apiKey.value='';s.modelSaved=true;saveModel.disabled=true;saveModel.textContent='AI setup saved';
      modelStatus.textContent=provider.value==='skip'?'AI setup saved for later.':'AI provider setup saved in Vishnu encrypted storage.';
      review.classList.add('hidden');
      $('enrollStatus').textContent='';
    } catch(error) { showError(error); }
  };

  reviewButton.onclick=()=>{
    if(!saved.checked)return showError(new Error('Confirm that you saved the recovery codes before reviewing setup.'));
    if(!s.policySaved)return showError(new Error('Save your data placement policy before reviewing setup.'));
    if(!s.modelSaved)return showError(new Error('Save your AI choice or select Configure later before reviewing setup.'));
    const owner=displayName.value.trim()||[firstName.value.trim(),lastName.value.trim()].filter(Boolean).join(' ')||'Vishnu Owner';
    const policyLabel=dataPolicy.options[dataPolicy.selectedIndex]?.textContent||dataPolicy.value;
    const providerLabel=provider.options[provider.selectedIndex]?.textContent||provider.value;
    const privacyLabel=privacy.options[privacy.selectedIndex]?.textContent||privacy.value;
    reviewSummary.textContent=[
      `Owner: ${owner}`,
      'First trusted device: this browser',
      'Security: owner password configured; passkey will be created now when supported',
      'Recovery: one-time codes saved and acknowledged',
      `Data placement: ${policyLabel}`,
      `Privacy: ${privacyLabel}`,
      `AI: ${providerLabel}${provider.value==='skip'?' (deferred)':model.value.trim()?` — ${model.value.trim()}`:''}`,
      'Autonomy: ask before acting',
    ].join('\n');
    review.classList.remove('hidden');
    review.scrollIntoView({behavior:'smooth',block:'nearest'});
    $('enrollStatus').textContent='Review the setup summary, then finish when it is correct.';
  };

  finish.onclick=async()=>{
    if(review.classList.contains('hidden'))return showError(new Error('Review your setup before finishing.'));
    if(!s.modelSaved)return showError(new Error('Save your AI choice or select Configure later before finishing.'));
    if(!s.policySaved)return showError(new Error('Save your data placement policy before finishing.'));
    if(!saved.checked)return showError(new Error('Confirm that you saved the recovery codes before continuing.'));
    const hasPasskey=Boolean(window.PublicKeyCredential&&navigator.credentials);let passkeyFallback=false;
    if(hasPasskey){
      try {
        const start=await api('/access/passkey/register/options',{method:'POST',body:'{}'});
        const credential=await navigator.credentials.create({publicKey:creationOptions(start.public_key)});
        await api('/access/passkey/register/complete',{method:'POST',body:JSON.stringify({challenge_id:start.challenge_id,credential:credentialJson(credential),name:'Vishnu browser passkey'})});
      } catch(error) { return showError(error.name==='NotAllowedError'?new Error('Passkey creation was cancelled. Try again.'):error); }
    } else {
      passkeyFallback=fallback.checked;
      if(!passkeyFallback)return showError(new Error('Confirm the password and recovery-code fallback to continue without a passkey.'));
    }
    try {
      await api('/first-run/complete',{method:'POST',body:JSON.stringify({recovery_saved:true,privacy_mode:privacy.value,autonomy_mode:'ask',passkey_unavailable_confirmed:passkeyFallback})});
      $('enrollStatus').textContent='';await window.check();
    } catch(error) { showError(error); }
  };
})();
