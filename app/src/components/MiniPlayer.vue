<template>
  <transition name="mp-slide">
    <div v-if="$store.state.miniPlayer.show && $store.state.miniPlayer.url"
         class="mini-player">
      <v-icon small class="mp-icon" :color="playing ? 'green' : 'grey'">
        {{ playing ? 'mdi-radio-tower' : 'mdi-pause-circle' }}
      </v-icon>
      <span class="mp-title text-truncate">{{ $store.state.miniPlayer.title }}</span>
      <v-btn x-small icon @click="toggle" class="mp-btn">
        <v-icon small>{{ playing ? 'mdi-pause' : 'mdi-play' }}</v-icon>
      </v-btn>
      <v-btn x-small icon @click="close" class="mp-btn">
        <v-icon small>mdi-close</v-icon>
      </v-btn>
      <audio ref="audio" :src="$store.state.miniPlayer.url" preload="none"
             @play="playing = true" @pause="playing = false"
             @error="onError" @ended="onEnded"></audio>
    </div>
  </transition>
</template>

<script>
export default {
  name: 'MiniPlayer',
  data: () => ({ playing: false }),
  watch: {
    '$store.state.miniPlayer.url'(url) {
      if (!url) { this.stopAudio(); return; }
      this.$nextTick(() => {
        const a = this.$refs.audio;
        if (!a) return;
        a.load();
        a.play().catch(() => {});
      });
    },
  },
  methods: {
    toggle() {
      const a = this.$refs.audio;
      if (!a) return;
      if (a.paused) { a.play().catch(() => {}); }
      else { a.pause(); }
    },
    close() {
      this.stopAudio();
      this.$store.commit('miniPlayer_hide');
    },
    stopAudio() {
      const a = this.$refs.audio;
      if (a) { a.pause(); a.src = ''; }
      this.playing = false;
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
.mp-btn { flex-shrink: 0; }
.mp-slide-enter-active, .mp-slide-leave-active { transition: transform .3s, opacity .3s; }
.mp-slide-enter, .mp-slide-leave-to { transform: translateY(100%); opacity: 0; }
</style>
