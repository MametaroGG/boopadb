"""Pure set reconciliation, not a source authenticator or visibility classifier.
Caller must independently derive all sets from immutable input/output bytes and
an approved real visibility classifier. These sets/return value confer NO authority.
No absolute/relative count tolerance. The connected byte adapter derives these sets.
"""
import re
class UnexplainedChange(ValueError):pass

def ids(values,label):
 if not isinstance(values,(list,tuple,set,frozenset)):raise UnexplainedChange(label+': explicit ID collection required')
 if any(not isinstance(v,str) or re.fullmatch('[1-9][0-9]*',v) is None for v in values):raise UnexplainedChange(label+': invalid product ID')
 if len(values)!=len(set(values)):raise UnexplainedChange(label+': duplicate product ID')
 return set(values)

def reconcile(previous_visible,candidate_visible,retained_backend,expected_frontend,confirmed_nonpublic,*,previous_backend):
 old=ids(previous_visible,'previous visible');new=ids(candidate_visible,'candidate visible')
 prior_backend=ids(previous_backend,'previous backend')
 backend=ids(retained_backend,'retained backend');expected=ids(expected_frontend,'independently expected frontend');hidden=ids(confirmed_nonpublic,'confirmed nonpublic')
 if not old<=prior_backend:raise UnexplainedChange('Previous visible ID absent from previous backend')
 if not prior_backend<=backend:raise UnexplainedChange('Previously retained backend product was lost')
 if not (new|expected|hidden)<=backend:raise UnexplainedChange('Output/classification ID absent from retained backend')
 if expected&hidden:raise UnexplainedChange('Conflicting public/nonpublic classification')
 if new!=expected:raise UnexplainedChange('Candidate differs from independently expected frontend IDs')
 removed=old-new;added=new-old
 if not removed<=backend:raise UnexplainedChange('Removed frontend product was deleted/lost from backend')
 if not removed<=hidden:raise UnexplainedChange('Visible product disappeared without confirmed nonpublic evidence')
 if new&hidden:raise UnexplainedChange('Nonpublic product still exposed')
 return {'status':'set-reconciliation-only-not-production-approval','previous_visible_count':len(old),'candidate_visible_count':len(new),'added_ids':sorted(added,key=int),'hidden_ids':sorted(removed,key=int),'count_delta':len(added)-len(removed),'new_backend_ids':sorted(backend-prior_backend,key=int),'new_visible_ids':sorted(added-prior_backend,key=int),'restored_frontend_ids':sorted(added&prior_backend,key=int),'backend_deletion_authorized':False}
