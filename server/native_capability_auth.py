from __future__ import annotations

import html

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse


def native_capability_auth_router(runtime):
    router = APIRouter(tags=["native-capability-auth"])
    sessions = runtime["pwa_sessions"]

    @router.get("/iphone/native/authorize", response_class=HTMLResponse)
    def authorize_page(client_id: str = Query(..., min_length=1, max_length=160),
                       redirect_uri: str = Query(..., min_length=1, max_length=1000),
                       code_challenge: str = Query(..., min_length=43, max_length=128),
                       state: str = Query(..., min_length=16, max_length=200)):
        if client_id not in sessions.native_client_redirects or redirect_uri not in sessions.native_client_redirects[client_id]:
            raise HTTPException(400, "Native application redirect is not registered")
        # The query values are escaped into attributes, and capability permissions
        # are chosen with an explicit owner gesture before any code is issued.
        cid, redirect, challenge, nonce = map(html.escape, (client_id, redirect_uri, code_challenge, state))
        page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Authorize Vishnu</title><body style="font:16px system-ui;max-width:36rem;margin:12vh auto;padding:1.5rem;background:#09111b;color:#edf2f7">
<main><h1>Connect this Vishnu app?</h1><p>Confirm the capabilities this app may manage. Access remains limited by this trusted device's permissions.</p>
<form id="grant" data-client="{cid}" data-redirect="{redirect}" data-challenge="{challenge}" data-state="{nonce}">
<label><input type="checkbox" name="scope" value="device:read" checked> View and test approved capabilities</label><br>
<label><input type="checkbox" name="scope" value="device:admin"> Manage connections, credentials, approvals, and permissions</label><br>
<button type="submit" style="margin-top:1rem;padding:.8rem 1.2rem">Authorize this app</button>
</form><p id="status" role="status" aria-live="polite">This grant uses a short-lived one-time code. Your session token is never placed in the redirect URL.</p>
<p><a href="/iphone/" style="color:#85c8ff">Open Vishnu sign-in</a></p></main>
<script>
const form=document.getElementById('grant'),status=document.getElementById('status');
form.addEventListener('submit',async event=>{{event.preventDefault();const scopes=[...form.querySelectorAll('input[name=scope]:checked')].map(x=>x.value);if(!scopes.length){{status.textContent='Select at least one permission.';return}}status.textContent='Checking owner session…';try{{const response=await fetch('/iphone/api/native/sessions/authorize',{{method:'POST',credentials:'same-origin',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{client_id:form.dataset.client,redirect_uri:form.dataset.redirect,code_challenge:form.dataset.challenge,scopes}})}});if(!response.ok){{if(response.status===401)throw new Error('Sign in to Vishnu in this browser, then return to this authorization page.')}}const result=await response.json();const target=new URL(result.redirect_uri);target.searchParams.set('code',result.code);target.searchParams.set('state',form.dataset.state);location.assign(target.toString())}}catch(error){{status.textContent=error.message||'Authorization could not be completed.'}}}});
</script></body></html>"""
        return HTMLResponse(page, headers={"Cache-Control": "no-store", "Pragma": "no-cache",
                                           "Referrer-Policy": "no-referrer",
                                           "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})

    @router.get("/.well-known/assetlinks.json")
    def android_association():
        links = runtime.get("android_asset_links", [])
        return JSONResponse(links, headers={"Cache-Control": "public, max-age=300"})

    @router.get("/.well-known/apple-app-site-association")
    def ios_association():
        association = runtime.get("apple_app_site_association", {})
        return JSONResponse(association, headers={"Cache-Control": "public, max-age=300"})

    return router
