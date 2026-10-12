import assert from 'node:assert/strict';
import opus from '/app/node_modules/@discordjs/opus/lib/index.js';
const { OpusEncoder } = opus;
import { VoiceDuckingController } from '/app/dist/bot/voice-ducking.js';

for (const codec of [4, 5]) {
  const channels = codec === 5 ? 2 : 1;
  const encoder = new OpusEncoder(48000, channels);
  let now = 0;
  const changes = [];
  const controller = new VoiceDuckingController(
    { setDuckingGain: (...args) => changes.push(args) },
    { enabled: true, volumePercent: 30 }, { now: () => now },
  );
  function packet(level) {
    const pcm = Buffer.alloc(960 * channels * 2);
    for (let frame = 0; frame < 960; frame++) {
      const value = Math.round(Math.sin(frame * 2 * Math.PI * 1000 / 48000) * level * 32767);
      for (let channel = 0; channel < channels; channel++) pcm.writeInt16LE(value, (frame * channels + channel) * 2);
    }
    return encoder.encode(pcm);
  }
  for (let i = 0; i < 100; i++) { controller.handleVoiceActivity(12, packet(0.001), codec); now += 20; }
  assert.equal(controller.isDucking(), false, 'continuous low noise must not duck');
  for (let i = 0; i < 5; i++) { controller.handleVoiceActivity(12, packet(0.02), codec); now += 20; }
  assert.equal(controller.isDucking(), true, 'audible speech must duck');
  assert.deepEqual(changes[0], [0.3, 50]);
  for (let i = 0; i < 20; i++) { controller.handleVoiceActivity(12, packet(0), codec); now += 20; }
  await new Promise(resolve => setTimeout(resolve, 200));
  assert.equal(controller.isDucking(), false, 'continuous silence must allow release');
  assert.deepEqual(changes.at(-1), [1, 500]);
  controller.handleVoiceActivity(12, Buffer.from([255]), codec);
  assert.equal(controller.isDucking(), false, 'invalid packets must not trigger ducking');
  controller.reset();
}
console.log('PASS: mono/stereo Opus, noise, speech, silence release and invalid packets');
