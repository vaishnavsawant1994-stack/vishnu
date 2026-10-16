# Third-Party Notices

Vishnu is proprietary software. The notices below apply only to the identified third-party components and do not grant rights to Vishnu's proprietary source code.

## REA (`rea-agents` 6.5.0)

Source: https://github.com/morluto/rea

MIT License

Copyright (c) 2026 morluto

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

REA can integrate with separately installed open-source and proprietary analysis engines. Those engines keep their own licenses and terms; Vishnu and REA do not grant licenses for commercial products such as IDA/Hex-Rays, Hopper, or JEB.

## OpenVoice

Source: https://github.com/myshell-ai/OpenVoice

Reviewed integration reference: `74a1d147b17a8c3092dd5430504bd83ef6c7eb23`

MIT License

Copyright 2024 MyShell.ai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Vishnu does not vendor OpenVoice in this repository. OpenVoice and its model assets are separately provisioned optional runtime components. Separate model checkpoints and transitive dependencies retain their own licenses and terms.

## VoiceStudio

Source: https://github.com/debpalash/VoiceStudio

License at the reviewed upstream `main`: GNU Affero General Public License v3 (AGPL-3.0).

Vishnu does not vendor, copy, modify, or redistribute VoiceStudio source code or model assets in this repository. The optional `voice/voicestudio.py` integration communicates with a separately installed VoiceStudio service through its documented HTTP/MCP network interfaces.

VoiceStudio engines, model checkpoints, and transitive dependencies retain their own licenses and terms. Before production distribution or hosted commercial use, review the exact VoiceStudio revision, deployment model, and every enabled engine/checkpoint license. VoiceStudio upstream states that a separate commercial license is available for closed-source/proprietary embedding; this Vishnu integration does not assume that such a license has been obtained.
