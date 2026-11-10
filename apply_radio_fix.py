#!/usr/bin/env python3
TARGET = '/volume1/docker/audiobook/app/src/components/MiniPlayer.vue'
with open(TARGET, encoding='utf-8') as f:
    lines = f.readlines()
out = []
i = 0
n = len(lines)
rh = False
ro = False
while i < n:
    st = lines[i].strip()
    if st.startswith('this.hls.on(Hls.Events.ERROR') and not rh:
        j = i
        while j < n and lines[j].strip() != '})':
            j += 1
        out.append('                this.hls.on(Hls.Events.ERROR, (evt, data) => {\n')
        out.append('                    if (!data || !data.fatal) return\n')
        out.append('                    switch (data.type) {\n')
        out.append('                        case Hls.ErrorTypes.NETWORK_ERROR:\n')
        out.append('                            this.hls.startLoad()\n')
        out.append('                            break\n')
        out.append('                        case Hls.ErrorTypes.MEDIA_ERROR:\n')
        out.append('                            this.hls.recoverMediaError()\n')
        out.append('                            break\n')
        out.append('                        default:\n')
        out.append("                            this.error = this.$t('miniPlayer.error')\n")
        out.append("                            this.$store.commit('miniPlayer_pause')\n")
        out.append('                    }\n')
        out.append('                })\n')
        rh = True
        i = j + 1
        continue
    if st.startswith('onError()') and not ro:
        j = i
        while j < n and lines[j].strip() != '},':
            j += 1
        out.append('        onError() {\n')
        out.append('            if (this.hls) return\n')
        out.append('            const audio = this.$refs.audio\n')
        out.append('            if (audio && audio.src && !this.recovering) {\n')
        out.append('                this.recovering = true\n')
        out.append('                const src = audio.src\n')
        out.append('                const wasPlaying = !audio.paused\n')
        out.append("                this.error = ''\n")
        out.append('                setTimeout(() => {\n')
        out.append('                    this.recovering = false\n')
        out.append('                    try {\n')
        out.append('                        audio.src = src\n')
        out.append('                        audio.load()\n')
        out.append('                        if (wasPlaying) audio.play().catch(() => {})\n')
        out.append('                    } catch (e) { /* ignore */ }\n')
        out.append('                }, 2000)\n')
        out.append('                return\n')
        out.append('            }\n')
        out.append("            this.error = this.$t('miniPlayer.error')\n")
        out.append("            this.$store.commit('miniPlayer_pause')\n")
        out.append('        },\n')
        ro = True
        i = j + 1
        continue
    out.append(lines[i])
    i += 1
if not rh or not ro:
    print('警告: hls=%s onError=%s 未匹配，未改动文件' % (rh, ro))
    sys.exit(1)
with open(TARGET, 'w', encoding='utf-8') as f:
    f.writelines(out)
print('OK: hls ERROR 处理 + onError 方法均已替换并写入 MiniPlayer.vue')
