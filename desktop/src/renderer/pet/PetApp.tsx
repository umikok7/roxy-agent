import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import {
  VRMAnimationLoaderPlugin,
  createVRMAnimationClip,
  type VRMAnimation,
} from "@pixiv/three-vrm-animation";
// import roxyVrmUrl from "../../../assets/roxy_3D/roxy_asset_3d.vrm?url";
import roxyVrmUrl from "../../../assets/roxy_3D/roxi.vrm?url";
import thinkingVrmaUrl from "../../../assets/roxy_3D/vrma/Thinking.vrma?url";
import lookAroundVrmaUrl from "../../../assets/roxy_3D/vrma/LookAround.vrma?url";
import RelaxVrmaUrl from "../../../assets/roxy_3D/vrma/Relax.vrma?url";
import AngryVrmaUrl from "../../../assets/roxy_3D/vrma/Angry.vrma?url";
import BlushVrmaUrl from "../../../assets/roxy_3D/vrma/Blush.vrma?url";
import ClappingVrmaUrl from "../../../assets/roxy_3D/vrma/Clapping.vrma?url";
import SleepyVrmaUrl from "../../../assets/roxy_3D/vrma/Sleepy.vrma?url";
import SadVrmaUrl from "../../../assets/roxy_3D/vrma/Sad.vrma?url";
import JumpVrmaUrl from "../../../assets/roxy_3D/vrma/Jump.vrma?url";
import SurprisedVrmaUrl from "../../../assets/roxy_3D/vrma/Surprised.vrma?url";
import GoodbyeVrmaUrl from "../../../assets/roxy_3D/vrma/Goodbye.vrma?url";

type PetVisualState = "thinking" | "lookAround";

type VrmaActionKey = "thinking" | "lookAround" | "random";

type LoadedVrm = {
  scene: THREE.Object3D;
  expressionManager?: {
    setValue?: (name: string, value: number) => void;
  };
  update?: (delta: number) => void;
};

type ActionPlaybackMode = "loop" | "hold";

const VRMA_ACTIONS: Record<VrmaActionKey, { url: string; label: string }> = {
  thinking: { url: thinkingVrmaUrl, label: "Thinking" },
  lookAround: { url: lookAroundVrmaUrl, label: "LookAround" },
  random: { url: "", label: "Random" },
};

const VRMA_RANDOM_ACTIONS: Record<string, { url: string; label: string }> = {
  relax: { url: RelaxVrmaUrl, label: "Relax" },
  angry: { url: AngryVrmaUrl, label: "Angry" },
  blush: { url: BlushVrmaUrl, label: "Blush" },
  clapping: { url: ClappingVrmaUrl, label: "Clapping" },
  sleepy: { url: SleepyVrmaUrl, label: "Sleepy" },
  sad: { url: SadVrmaUrl, label: "Sad" },
  jump: { url: JumpVrmaUrl, label: "Jump" },
  surprised: { url: SurprisedVrmaUrl, label: "Surprised" },
  goodbye: { url: GoodbyeVrmaUrl, label: "Goodbye" },
};

function damp(current: number, target: number, lambda: number, delta: number) {
  return THREE.MathUtils.lerp(current, target, 1 - Math.exp(-lambda * delta));
}

async function loadVrmModel(loader: GLTFLoader) {
  const gltf = await loader.loadAsync(roxyVrmUrl);
  const vrm = gltf.userData.vrm as LoadedVrm | undefined;

  if (!vrm) {
    throw new Error("VRM asset did not expose a VRM instance");
  }

  VRMUtils.rotateVRM0(vrm as never);
  VRMUtils.combineSkeletons(vrm.scene);
  VRMUtils.combineMorphs(vrm as never);

  return vrm;
}

async function loadVrmaClip(loader: GLTFLoader, vrm: LoadedVrm, url: string) {
  const gltf = await loader.loadAsync(url);
  const vrmAnimations = gltf.userData.vrmAnimations as VRMAnimation[] | undefined;
  const vrmAnimation = vrmAnimations?.[0];

  if (!vrmAnimation) {
    throw new Error("VRMA asset did not expose a VRMAnimation instance");
  }

  const clip = createVRMAnimationClip(vrmAnimation, vrm as never);
  clip.name = `vrma:${url.split("/").pop() || "action"}`;
  return clip;
}

export default function PetApp() {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stateRef = useRef<PetVisualState>("lookAround");

  useEffect(() => {
    const stopCurrentAudio = () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
        audioRef.current = null;
      }
    };

    const unsubscribe = window.electronAPI.onPlayVoiceAsset((payload) => {
      if (!payload?.assetUrl) return;

      stopCurrentAudio();
      const audio = new Audio(payload.assetUrl);
      audioRef.current = audio;
      void audio.play().catch((error) => {
        console.error("Failed to play voice asset:", error);
      });
    });

    return () => {
      unsubscribe();
      stopCurrentAudio();
    };
  }, []);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let disposed = false;
    let frameId = 0;
    let mixer: THREE.AnimationMixer | null = null;
    let vrm: LoadedVrm | null = null;
    let activeAction: THREE.AnimationAction | null = null;
    let activeActionKey: VrmaActionKey | null = null;
    const actionMap = new Map<VrmaActionKey, THREE.AnimationAction>();
    let blinkTimer = 1.4;
    let blinkWeight = 0;
    let mouthPhase = 0;
    let currentRootYaw = 0;
    let currentRootPitch = 0;
    let currentRootRoll = 0;
    const baseFacingYaw = Math.PI;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);
    camera.position.set(0.5, 1.35, 4.2);

    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4);
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.15);
    keyLight.position.set(1.25, 2.8, 3.2);
    const fillLight = new THREE.DirectionalLight(0xe8f0ff, 0.45);
    fillLight.position.set(-1.5, 1.8, 1.5);
    scene.add(ambientLight, keyLight, fillLight);

    const clock = new THREE.Clock();

    const resize = () => {
      if (!container) return;
      const width = container.clientWidth || 1;
      const height = container.clientHeight || 1;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };

    const frameBox = (root: THREE.Object3D) => {
      const bounds = new THREE.Box3().setFromObject(root);
      const size = bounds.getSize(new THREE.Vector3());
      const center = bounds.getCenter(new THREE.Vector3());

      root.position.x -= center.x;
      root.position.y -= bounds.min.y + size.y * 0.02;
      root.position.z -= center.z;

      const fullHeight = Math.max(size.y, 1);
      const fullWidth = Math.max(size.x, 0.65);
      camera.position.set(fullWidth * 0.32, fullHeight * 0.6, Math.max(fullHeight * 2.15, 3.4));
      camera.lookAt(0, fullHeight * 0.52, 0);
    };

    const fadeOutActiveAction = () => {
      if (activeAction) {
        activeAction.fadeOut(0.15);
      }
    };

    const activateAction = (key: VrmaActionKey, mode: ActionPlaybackMode) => {
      const nextAction = actionMap.get(key);
      if (!nextAction) return;

      if (activeAction && activeAction !== nextAction) {
        fadeOutActiveAction();
      }

      nextAction.stopFading();
      nextAction.enabled = true;
      nextAction.reset();
      nextAction.setEffectiveWeight(1);
      nextAction.paused = false;

      if (mode === "loop") {
        nextAction.loop = THREE.LoopRepeat;
        nextAction.repetitions = Infinity;
        nextAction.clampWhenFinished = false;
        nextAction.play();
      } else {
        nextAction.loop = THREE.LoopOnce;
        nextAction.repetitions = 1;
        nextAction.clampWhenFinished = false;
        nextAction.play();
        mixer?.update(0);
        nextAction.paused = true;
      }

      activeAction = nextAction;
      activeActionKey = key;
    };

    const unsubscribeStateChange = window.electronAPI.onStateChange((state) => {
      stateRef.current = state;
      activateAction(state, state === "thinking" ? "loop" : "hold");
    });

    const unsubscribeRandomAction = window.electronAPI.onPlayRandomAction((actionKey, assetUrl) => {
      console.log('[PetApp] onPlayRandomAction received:', actionKey, assetUrl);
      if (!actionKey || !assetUrl || !vrm || !mixer) {
        console.log('[PetApp] early return: vrm=', !!vrm, 'mixer=', !!mixer);
        return;
      }
      const vrmaLoader = new GLTFLoader();
      vrmaLoader.register((parser: any) => new VRMAnimationLoaderPlugin(parser));
      loadVrmaClip(vrmaLoader, vrm, assetUrl).then((clip) => {
        console.log('[PetApp] clip loaded, creating action');
        if (disposed || !mixer) return;
        const tempAction = mixer.clipAction(clip);
        tempAction.clampWhenFinished = false;
        tempAction.loop = THREE.LoopOnce;
        tempAction.repetitions = 1;
        tempAction.play();
        // After action finishes, revert to lookAround
        const onFinished = () => {
          console.log('[PetApp] action finished, reverting to lookAround');
          tempAction.stop();
          activateAction("lookAround", "hold");
          mixer?.removeEventListener("finished", onFinished);
        };
        mixer?.addEventListener("finished", onFinished);
      }).catch((err) => {
        console.error("[PetApp] Failed to load random action:", err);
      });
    });

    const applyStateAnimation = (delta: number, elapsed: number) => {
      if (!vrm) return;

      const isThinking = stateRef.current === "thinking";
      const desiredYaw = isThinking ? 0.22 : 0.08;
      const desiredPitch = isThinking ? -0.08 : -0.02;

      currentRootYaw = damp(currentRootYaw, desiredYaw, 4.5, delta);
      currentRootPitch = damp(currentRootPitch, desiredPitch, 4.5, delta);
      currentRootRoll = damp(currentRootRoll, 0, 4.5, delta);

      vrm.scene.rotation.y =
        baseFacingYaw + currentRootYaw + Math.sin(elapsed * 0.6) * (isThinking ? 0.015 : 0.045);
      vrm.scene.rotation.x = currentRootPitch + Math.sin(elapsed * 1.4) * (isThinking ? 0.004 : 0.01);
      vrm.scene.rotation.z = currentRootRoll + Math.sin(elapsed * 0.7) * 0.008;
      vrm.scene.position.y = Math.sin(elapsed * (isThinking ? 1.85 : 1.35)) * (isThinking ? 0.012 : 0.02);

      if (activeAction && activeActionKey === "thinking") {
        activeAction.setEffectiveTimeScale(1.05);
        activeAction.setEffectiveWeight(1);
      } else if (activeAction) {
        activeAction.setEffectiveTimeScale(1);
        activeAction.setEffectiveWeight(1);
      }

      blinkTimer -= delta;
      if (blinkTimer <= 0) {
        blinkWeight = 1;
        blinkTimer = 2.5 + Math.random() * 2.2;
      }
      blinkWeight = Math.max(0, blinkWeight - delta * 6.5);
      vrm.expressionManager?.setValue?.("blink", blinkWeight);

      if (audioRef.current && !audioRef.current.paused) {
        mouthPhase += delta * 20;
        const mouthWeight = 0.15 + Math.max(0, Math.sin(mouthPhase)) * 0.35;
        vrm.expressionManager?.setValue?.("aa", mouthWeight);
        vrm.expressionManager?.setValue?.("oh", mouthWeight * 0.45);
      } else {
        mouthPhase = 0;
        vrm.expressionManager?.setValue?.("aa", 0);
        vrm.expressionManager?.setValue?.("oh", 0);
      }
    };

    const animate = () => {
      if (disposed) return;

      const delta = Math.min(clock.getDelta(), 1 / 30);
      const elapsed = clock.elapsedTime;

      mixer?.update(delta);
      applyStateAnimation(delta, elapsed);
      vrm?.update?.(delta);
      renderer.render(scene, camera);
      frameId = window.requestAnimationFrame(animate);
    };

    const init = async () => {
      try {
        const loader = new GLTFLoader();
        loader.register((parser: any) => new VRMLoaderPlugin(parser));

        vrm = await loadVrmModel(loader);
        if (disposed) return;

        scene.add(vrm.scene);
        frameBox(vrm.scene);

        mixer = new THREE.AnimationMixer(vrm.scene);

        const vrmaLoader = new GLTFLoader();
        vrmaLoader.register((parser: any) => new VRMAnimationLoaderPlugin(parser));

        const entries = (Object.entries(VRMA_ACTIONS) as [VrmaActionKey, { url: string; label: string }][])
            .filter(([key]) => key !== "random");
        await Promise.all(
          entries.map(async ([key, entry]) => {
            const clip = await loadVrmaClip(vrmaLoader, vrm, entry.url);
            if (disposed || !mixer) return;
            const nextAction = mixer.clipAction(clip);
            nextAction.clampWhenFinished = false;
            actionMap.set(key, nextAction);
          }),
        );

        if (!disposed) {
          activateAction(stateRef.current, stateRef.current === "thinking" ? "loop" : "hold");
          resize();
          animate();
        }
      } catch (error) {
        console.error("Failed to initialize 3D pet:", error);
      }
    };

    const handleResize = () => resize();
    window.addEventListener("resize", handleResize);
    init();

    return () => {
      disposed = true;
      unsubscribeStateChange();
      unsubscribeRandomAction?.();
      window.removeEventListener("resize", handleResize);
      window.cancelAnimationFrame(frameId);
      mixer?.stopAllAction();
      renderer.dispose();
      container.removeChild(renderer.domElement);
      scene.traverse((child: THREE.Object3D) => {
        const mesh = child as THREE.Mesh;
        if (!mesh.geometry || !mesh.material) return;
        mesh.geometry.dispose();
        if (Array.isArray(mesh.material)) {
          mesh.material.forEach((material: THREE.Material) => material.dispose());
        } else {
          mesh.material.dispose();
        }
      });
    };
  }, []);

  return <div ref={mountRef} id="pet-canvas-shell" aria-label="Roxy 3D pet" />;
}
