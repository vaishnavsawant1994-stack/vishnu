from __future__ import annotations
import json,threading,uuid
from datetime import datetime,timezone
from pathlib import Path

DEFAULTS={
    'onboarding_complete':False,
    'preferred_name':'',
    'profile_first_name':'',
    'profile_last_name':'',
    'owner_account_id':'',
    'owner_account_created_at':'',
    'wake_phrase':'Hey Personal',
    'launch_voice_on_start':False,
    'show_memory_hints':True,
    'reduce_motion':False,
    'high_contrast':False,
    'autonomy_mode':'ask',
    'model_privacy_mode':'local_preferred',
    'memory_enabled':True,
    'review_memory_before_saving':True,
    'share_anonymous_usage_data':False,
    'notifications_preferences':{},
    # Optional adaptive intelligence. STANDARD + disabled preserves the
    # historical single-route Vishnu behavior. Training capture is ON by
    # default, while governed eligibility/privacy/provenance/quality filters
    # still decide whether any captured candidate may enter a dataset.
    'advanced_intelligence_enabled':False,
    'intelligence_mode':'standard',
    'intelligence_auto_escalation':False,
    'intelligence_verification_enabled':True,
    'intelligence_training_capture':True,
    # Added with the corrected ON-by-default policy. Presence of this key lets
    # us distinguish a legacy implicit false from a later real owner OFF choice.
    'intelligence_training_capture_owner_configured':False,
    'intelligence_performance_learning':True,
    'intelligence_max_models':5,
    'intelligence_latency_preference':'balanced',
    'intelligence_max_cost_per_request':None,
}

class Preferences:
    def __init__(self,path:Path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);is_new_install=not self.path.exists();self.lock=threading.RLock();self.data=dict(DEFAULTS);self._loaded_keys=set();self._load()
        changed=False
        # The previous implementation wrote Training Capture=False as a default
        # even when the owner never made a choice. Migrate that implicit legacy
        # state to the corrected ON default exactly once. Future owner OFF
        # choices persist because the marker is then present/configured.
        if not is_new_install and 'intelligence_training_capture_owner_configured' not in self._loaded_keys:
            self.data['intelligence_training_capture']=True
            self.data['intelligence_training_capture_owner_configured']=False
            changed=True
        if not self.data.get('owner_account_id'):
            self.data['owner_account_id']=uuid.uuid4().hex;changed=True
        if is_new_install and not self.data.get('owner_account_created_at'):
            self.data['owner_account_created_at']=datetime.now(timezone.utc).isoformat();changed=True
        if not self.data.get('profile_first_name') and not self.data.get('profile_last_name') and self.data.get('preferred_name'):
            name=str(self.data['preferred_name']).strip().split()
            if name:
                self.data['profile_first_name']=name[0]
                self.data['profile_last_name']=' '.join(name[1:]) or name[0]
                changed=True
        if changed:self._save()
    def _load(self):
        if not self.path.exists():return
        try:
            value=json.loads(self.path.read_text())
            if isinstance(value,dict):
                self._loaded_keys=set(value)
                self.data.update({k:v for k,v in value.items() if k in DEFAULTS})
        except Exception:pass
    def get(self,key,default=None):return self.data.get(key,default)
    def set(self,key,value):
        if key not in DEFAULTS:raise KeyError(key)
        with self.lock:self.data[key]=value;self._save()
    def update(self,**values):
        unknown=set(values)-set(DEFAULTS)
        if unknown:raise KeyError(sorted(unknown))
        with self.lock:self.data.update(values);self._save()
    def _save(self):
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.data,sort_keys=True,indent=2));tmp.replace(self.path)
    def snapshot(self):return dict(self.data)
