/* Universal browser first-run adapter. All identity and security state remains
   in FirstRunCoordinator, OwnerAccessStore, DeviceRegistry, the Data Plane,
   and the model vault. */
(() => {
  const $ = id => document.getElementById(id);
  const originalLoadAccessOptions = window.loadAccessOptions;
  const originalCheck = window.check;
  if (typeof originalLoadAccessOptions !== 'function' || typeof originalCheck !== 'function') return;
  let options = {};
  let modelSaved = false;
  let policySaved = false;
  const choices = document.createElement('div');
  choices.id = 'firstRunChoices';
  choices.className = 'access-form hidden';
  const createChoice = document.createElement('button');
  createChoice.type = 'button';
  createChoice.className = 'secondary';
  const joinChoice = document.createElement('button');
  joinChoice.type = 'button';
  joinChoice.className = 'secondary';
  joinChoice.textContent = 'I already have Vishnu';
  const restoreChoice = document.createElement('button');
  restoreChoice.type = 'button';
  restoreChoice.className = 'secondary';
  restoreChoice.textContent = 'Restore Vishnu';
  const createForm = document.createElement('div');
  createForm.id = 'firstRunForm';
  createForm.className = 'access-form hidden';
  choices.append(createChoice, joinChoice, createForm);
  const accessMethods = document.querySelector('#enrollPanel .access-methods');
  accessMethods?.prepend(choices);
  // Recovery is also an entry path for initialized Vishnu instances, so keep
  // Restore visible after creation is disabled as well.
  accessMethods?.append(restoreChoice);

  const field = (id, placeholder, type = 'text', autocomplete = 'off') => {
    const input = document.createElement('input');
    input.id = id;
    input.type = type;
    input.autocomplete = autocomplete;
    input.placeholder = placeholder;
    return input;
  };
  const button = (id, label, secondary = false) => {
    const value = document.createElement('button');
    value.id = id;
    value.type = 'button';
    value.textContent = label;
    if (secondary) value.className = 'secondary';
    return value;
  };
  const label = (text, control) => {
    const value = document.createElement('label');
    value.className = 'access-note';
    value.textContent = text;
    value.htmlFor = control.id;
    return value;
  };
  const heading = text => {
    const value = document.createElement('h3');
    value.textContent = text;
    value.className = 'access-heading';
    return value;
  };
  const firstName = field('firstRunFirstName', 'First name', 'text', 'given-name');
  const lastName = field('firstRunLastName', 'Last name (optional)', 'text', 'family-name');
  const displayName = field('firstRunDisplayName', 'Display name (optional)', 'text', 'nickname');
  const bootstrap = field('firstRunBootstrap', 'Vishnu runtime setup code', 'password', 'one-time-code');
  const password = field('firstRunPassword', 'Owner password (12 characters minimum)', 'password', 'new-password');
  const passwordAgain = field('firstRunPasswordAgain', 'Confirm owner password', 'password', 'new-password');
  const begin = button('firstRunBegin', 'Create Vishnu identity');
  const recovery = document.createElement('section');
  recovery.id = 'firstRunRecovery';
  recovery.className = 'hidden';
  const recoveryIntro = document.createElement('p');
  recoveryIntro.className = 'access-note';
  recoveryIntro.textContent = 'Save these one-time recovery codes somewhere outside this browser. Each code can be used once.';
  const codes = document.createElement('pre');
  codes.className = 'recovery-codes';
  const savedLabel = document.createElement('label');
  savedLabel.className = 'access-note';
  const saved = document.createElement('input');
  saved.type = 'checkbox';
  saved.id = 'firstRunRecoverySaved';
  savedLabel.append(saved, document.createTextNode(' I saved these codes somewhere safe.'));
  const privacy = document.createElement('select');
  privacy.id = 'firstRunPrivacy';
  for (const [value, text] of [['local_only','Local only'],['local_preferred','Local preferred'],['external_allowed','External providers allowed']]) {
    const option = document.createElement('option'); option.value = value; option.textContent = text; privacy.append(option);
  }

  const dataPolicy = document.createElement('select');
  dataPolicy.id = 'firstRunDataPolicy';
  for (const [value, text] of [
    ['device_only','Device only — keep governed data on this device'],
    ['progress_only','Progress only — share only continuation/progress data'],
    ['sync_everywhere','Sync everywhere — sync permitted data to trusted locations'],
    ['on_demand','On demand — move data only when explicitly required'],
  ]) {
    const option = document.createElement('option'); option.value = value; option.textContent = text; dataPolicy.append(option);
  }
  const savePolicy = button('firstRunSavePolicy','Save data placement',true);
  const policyStatus = document.createElement('p');
  policyStatus.className = 'access-note';
  policyStatus.textContent = 'Changing this default never silently moves data that already exists.';

  const provider = document.createElement('select');
  provider.id = 'firstRunProvider';
  for (const [value, text] of [['skip','Configure later'],['local','Local model'],['openai','OpenAI'],['gemini','Gemini'],['openrouter','OpenRouter'],['deepseek','DeepSeek'],['xai','xAI'],['groq','Groq'],['cerebras','Cerebras'],['mistral','Mistral'],['custom','Custom provider']]) {
    const option = document.createElement('option'); option.value = value; option.textContent = text; provider.append(option);
  }
  const model = field('firstRunModel','Model name (required for provider setup)');
  const apiKey = field('firstRunApiKey','Provider API key (saved in Vishnu encrypted storage)','password','new-password');
  model.classList.add('hidden'); apiKey.classList.add('hidden');
  const saveModel = button('firstRunSaveModel','Save AI setup choice',true);
  const modelStatus = document.createElement('p'); modelStatus.className = 'access-note';
  modelStatus.textContent = 'Choose a local model, connect an AI provider, or select Configure later.';
  const passkeyHint = document.createElement('p'); passkeyHint.className = 'access-note';
  const fallbackLabel = document.createElement('label'); fallbackLabel.className = 'access-note hidden';
  const fallback = document.createElement('input'); fallback.type = 'checkbox'; fallback.id = 'firstRunFallback';
  fallbackLabel.append(fallback, document.createTextNode(' This browser cannot create a passkey; continue with the owner password and saved recovery codes.'));

  const reviewButton = button('firstRunReviewButton','Review setup');
  const review = document.createElement('section');
  review.id = 'firstRunReview';
  review.className = 'hidden';
  const reviewIntro = document.createElement('p');
  reviewIntro.className = 'access-note';
  reviewIntro.textContent = 'Review the owner, security, recovery, data placement, privacy and AI choices before Vishnu becomes ready.';
  const reviewSummary = document.createElement('pre');
  reviewSummary.id = 'firstRunReviewSummary';
  reviewSummary.className = 'recovery-codes';
  const finish = button('firstRunFinish','Finish setup');
  review.append(heading('Review and finish'), reviewIntro, reviewSummary, passkeyHint, fallbackLabel, finish);

  recovery.append(
    heading('Recovery'), recoveryIntro, codes, savedLabel,
    heading('Privacy and autonomy'), label('Model privacy', privacy), privacy,
    heading('Data placement'), label('Where may newly governed data live?', dataPolicy), dataPolicy,
    savePolicy, policyStatus,
    heading('AI provider'), label('AI setup', provider), provider, model, apiKey, saveModel, modelStatus,
    reviewButton, review,
  );
  createForm.append(
    document.createElement('p'), firstName, lastName, displayName, bootstrap, password,
    passwordAgain, begin, recovery,
  );
  createForm.firstChild.className = 'access-note';
  createForm.firstChild.textContent = 'This browser connects to an already deployed Vishnu runtime; it does not host the runtime. The setup code is supplied by the runtime operator.';

  const showError = error => { const status = $('enrollStatus'); if (status) status.textContent = error?.message || 'Vishnu setup could not continue.'; };
  function refreshChoices() {
    const available = Boolean(options.creation_available);
    choices.classList.toggle('hidden', !available);
    createChoice.textContent = options.setup_in_progress ? 'Resume creating my Vishnu' : 'Create my Vishnu';
    $('enrollHeading').textContent = available ? 'Welcome to Vishnu' : 'Welcome back';
    $('enrollIntro').textContent = available ? 'Create your Vishnu on this runtime or connect to the one you already have.' : 'Unlock your owner-controlled Vishnu.';
    modelSaved = Boolean(options.model_setup_complete);
    if (modelSaved) { saveModel.disabled = true; saveModel.textContent = 'AI setup saved'; }
    const browserPasskey = Boolean(window.PublicKeyCredential && navigator.credentials);
    passkeyHint.textContent = browserPasskey
      ? 'Recommended: create a passkey with this browser or device authenticator. It belongs to your Vishnu owner identity.'
      : 'This browser cannot create a passkey. Use the owner password and saved recovery codes as independent protection.';
    fallbackLabel.classList.toggle('hidden', browserPasskey);
  }
  window.loadAccessOptions = async function (...args) {
    options = await originalLoadAccessOptions(...args) || {};
    refreshChoices();
    return options;
  };
  window.check = async function (...args) {
    const result = await originalCheck(...args);
    try {
      options = await originalLoadAccessOptions() || {};
      refreshChoices();
      if (options.creation_available) {
        $('enrollPanel').classList.remove('hidden');
        $('voicePanel').classList.add('hidden');
        $('features').classList.add('hidden');
      }
    } catch { }
    return result;
  };
  window.vishnuFirstRun = {
    $, createChoice, joinChoice, restoreChoice, createForm, firstName, lastName, displayName, bootstrap,
    password, passwordAgain, begin, codes, recovery, saved, privacy, dataPolicy, savePolicy, policyStatus,
    provider, model, apiKey, saveModel, modelStatus, fallback, reviewButton, review, reviewSummary,
    finish, showError,
    get modelSaved() { return modelSaved; }, set modelSaved(value) { modelSaved = Boolean(value); },
    get policySaved() { return policySaved; }, set policySaved(value) { policySaved = Boolean(value); },
  };
  window.loadAccessOptions().then(refreshChoices).catch(()=>{});
  window.check().catch(()=>{});
})();
