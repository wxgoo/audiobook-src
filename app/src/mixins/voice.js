/**
 * 麦克风语音输入 mixin
 *
 * 供 AI 输入框（AppHeader）与 MyNexus 对话框（MyNexusChatDialog）共用。
 * 录音走浏览器 MediaRecorder，停止后把音频 POST 到后端
 * /api/assistant/transcribe（本地 faster-whisper）转写成文字，
 * 追加写入 voiceTargetField 指定的输入框字段。
 *
 * 注意：getUserMedia 只在 HTTPS / localhost 安全上下文可用；
 * HTTP + IP 访问时 voiceSupported 为 false，麦克风按钮不显示。
 */
export default {
    data() {
        return {
            voiceRecording: false,
            voiceBusy: false,
            voiceError: "",
            voiceTargetField: "",
            _voiceRecorder: null,
            _voiceChunks: [],
            _voiceStream: null,
        };
    },
    computed: {
        voiceSupported() {
            return typeof window !== "undefined" && !!(
                navigator.mediaDevices &&
                navigator.mediaDevices.getUserMedia &&
                window.MediaRecorder
            );
        },
    },
    beforeDestroy() {
        this._voiceStopStream();
    },
    methods: {
        async toggleVoice() {
            if (this.voiceBusy) return;
            if (this.voiceRecording) {
                this.stopVoice();
                return;
            }
            await this.startVoice();
        },
        async startVoice() {
            this.voiceError = "";
            if (!this.voiceSupported) {
                this.voiceError = "当前浏览器不支持录音（需 HTTPS 或 localhost + Chrome/Edge）";
                return;
            }
            let stream;
            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                this._voiceStream = stream;
                this._voiceChunks = [];
                let mimeType = "";
                const candidates = [
                    "audio/webm;codecs=opus",
                    "audio/webm",
                    "audio/ogg;codecs=opus",
                    "audio/mp4",
                ];
                for (const mt of candidates) {
                    if (!window.MediaRecorder.isTypeSupported) continue;
                    if (!window.MediaRecorder.isTypeSupported(mt)) continue;
                    mimeType = mt;
                    break;
                }
                const opts = mimeType ? { mimeType } : undefined;
                this._voiceRecorder = new MediaRecorder(stream, opts);
                this._voiceRecorder.ondataavailable = (e) => {
                    if (e.data && e.data.size > 0) this._voiceChunks.push(e.data);
                };
                this._voiceRecorder.onstop = () => this._onVoiceStopped();
                this._voiceRecorder.start();
                this.voiceRecording = true;
            } catch (err) {
                this.voiceError = "无法访问麦克风：" + (err && err.message ? err.message : err);
            }
        },
        stopVoice() {
            if (this._voiceRecorder && this._voiceRecorder.state !== "inactive") {
                this._voiceRecorder.stop();
            }
            this.voiceRecording = false;
            this._voiceStopStream();
        },
        _voiceStopStream() {
            if (this._voiceStream) {
                try {
                    this._voiceStream.getTracks().forEach((t) => t.stop());
                } catch (e) {
                    // ignore
                }
                this._voiceStream = null;
            }
        },
        async _onVoiceStopped() {
            this.voiceBusy = true;
            try {
                const blob = new Blob(this._voiceChunks, {
                    type: (this._voiceChunks[0] && this._voiceChunks[0].type) || "audio/webm",
                });
                if (!blob.size) {
                    this.voiceError = "没录到声音";
                    return;
                }
                const ct = blob.type || "";
                const ext = ct.includes("mp4") ? "m4a" : (ct.includes("ogg") ? "ogg" : "webm");
                const form = new FormData();
                form.append("audio", blob, "voice." + ext);
                const res = await this.$backend(
                    "/assistant/transcribe?model=small&lang=auto",
                    { method: "POST", body: form }
                );
                if (res && res.err === "ok" && res.text) {
                    const field = this.voiceTargetField || "ai_input";
                    const cur = (this[field] || "").trim();
                    this[field] = cur ? cur + " " + res.text : res.text;
                } else {
                    this.voiceError = (res && res.msg) || "语音识别失败";
                }
            } catch (err) {
                this.voiceError = "语音识别失败：" + (err && err.message ? err.message : err);
            } finally {
                this.voiceBusy = false;
            }
        },
    },
};
