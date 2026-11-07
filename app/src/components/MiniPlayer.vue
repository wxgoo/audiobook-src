<template>
  <transition name="mp-slide">
    <div v-if="$store.state.miniPlayer.show && $store.state.miniPlayer.url"
         class="mini-player">
      <v-icon small class="mp-icon" :color="playing ? 'green' : 'grey'">
        {{ playing ? 'mdi-volume-high' : 'mdi-volume-off' }}
      </v-icon>
      <span class="mp-title text-truncate">{{ $store.state.miniPlayer.title }}</span>
      <span v-if="currentTime" class="mp-time text-caption grey--text">{{ fmt(currentTime) }}</span>
      <v-btn x-small icon @click="toggle" class="mp-btn">
        <v-icon small>{{ playing ? 'mdi-pause' : 'mdi-play' }}</v-icon>
      </v-btn>
      <v-btn x-small icon @click="close" class="mp-btn">
        <v-icon small>mdi-close</v-icon>
      </v-btn>
      <audio ref="audio" preload="none"
             @play="playing = true" @pause="playing = false"
             @error="onError" @ended="onEnded" @timeupdate="onTimeUpdate"></audio>
    </div>
  </transition>
</template>

<script>
// 全局置顶迷你播放条：不管在哪个页面都显示在底部，音频持续播放。
// 支持直连音频流（mp3/aac/wav）和 HLS（m3u8，自动加载 hls.js）。
// 有声书播放页可通过 commit('miniPlayer_play', {..., startTime}) 收起到底部。

let hlsLib = null;   // 缓存已加载的 hls.js 模块
let hlsLoading = false;
const hlsCallbacks = [];

function loadHlsJs(cb) {
  if (hlsLib) return cb(hlsLib);
  if (hlsLoading) { hlsCallbacks.push(cb); return; }
  hlsLoading = true;
  hlsCallbacks.push(cb);
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/hls.js@1/dist/hls.min.js';
  s.onload = () => {
    hlsLib = window.Hls;
    hlsLoading = false;
    hlsCallbacks.forEach(fn => fn(hlsLib));
    hlsCallbacks.length = 0;
  };
  s.onerror = () => {
    hlsLoading = false;
    hlsCallbacks.forEach(fn => fn(null));
    hlsCallbacks.length = 0;
  };
  document.head.appendChild(s);
}

export default {
  name: 'MiniPlayer',
  data: () => ({ playing: false, currentTime: 0, hls: null }),
  watch: {
    '$store.state.miniPlayer.url'(url) {
      if (!url) { this.stopAudio(); return; }
      this.$nextTick(() => this.play(url, this.$store.state.miniPlayer.startTime || 0));
    },
  },
  beforeDestroy() {
    if (this.hls) { this.hls.destroy(); this.hls = null; }
  },
  methods: {
    fmt(sec) {
      if (!sec || !isFinite(sec)) return '';
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return m + ':' + String(s).padStart(2, '0');
    },
    isHls(url) { return url.includes('.m3u8') || url.includes('/hls/'); },

    play(url, startTime = 0) {
      const a = this.$refs.audio;
      if (!a) return;
      // 清理上一次的 hls 实例
      if (this.hls) { this.hls.destroy(); this.hls = null; }
      a.pause();

      if (this.isHls(url)) {
        // m3u8：加载 hls.js 或用 Safari 原生支持
        loadHlsJs((Hls) => {
          if (Hls && Hls.isSupported()) {
            this.hls = new Hls();
            this.hls.loadSource(url);
            this.hls.attachMedia(a);
            this.hls.on(Hls.Events.MANIFEST_PARSED, () => {
              if (startTime > 0) a.currentTime = startTime;
              a.play().catch(() => {});
            });
          } else if (a.canPlayType('application/vnd.apple.mpegurl')) {
            a.src = url;
            if (startTime > 0) a.currentTime = startTime;
            a.play().catch(() => {});
          } else {
            this.$store.commit('alert', { type: 'error', msg: this.$t('miniPlayer.hlsError'), show: true, to: '' });
          }
        });
      } else {
        a.src = url;
        a.load();
        if (startTime > 0) {
          a.addEventListener('loadedmetadata', () => { a.currentTime = startTime; }, { once: true });
        }
        a.play().catch(() => {});
      }
    },

    toggle() {
      const a = this.$refs.audio;
      if (!a || !a.src) return;
      if (a.paused) { a.play().catch(() => {}); }
      else { a.pause(); }
    },
    close() {
      if (this.hls) { this.hls.destroy(); this.hls = null; }
      const a = this.$refs.audio;
      if (a) { a.pause(); a.src = ''; }
      this.playing = false;
      this.currentTime = 0;
      this.$store.commit('miniPlayer_hide');
    },
    stopAudio() {
      if (this.hls) { this.hls.destroy(); this.hls = null; }
      const a = this.$refs.audio;
      if (a) { a.pause(); a.src = ''; }
      this.playing = false;
    },
    onTimeUpdate() {
      const a = this.$refs.audio;
      if (a) this.currentTime = a.currentTime;
    },
    onError() {
      this.playing = false;
      this.$store.commit('alert', {
        type: 'error', msg: this.$t('miniPlayer.error'), show: true, to: '',
      });
    },
    onEnded() { this.playing = false; },
  },
};
</script>

<style scoped>
.mini-player {
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000;
  background: #1a1a2e; color: #eee;
  display: flex; align-items: center; gap: 10px;
  padding: 6px 16px; min-height: 42px;
  border-top: 2px solid #1976d2;
  box-shadow: 0 -2px 8px rgba(0,0,0,.5);
}
.mp-icon { flex-shrink: 0; }
.mp-title { flex: 1; min-width: 0; font-size: 13px; }
.mp-time { flex-shrink: 0; font-family: monospace; }
.mp-btn { flex-shrink: 0; }
.mp-slide-enter-active, .mp-slide-leave-active { transition: transform .3s, opacity .3s; }
.mp-slide-enter, .mp-slide-leave-to { transform: translateY(100%); opacity: 0; }
</style>
