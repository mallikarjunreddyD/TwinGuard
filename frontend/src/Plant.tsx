import {useEffect,useRef} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {colors,severity} from './semantics';
export function Plant({token,conditions,regions,onSelect}:{token:string,conditions:Record<string,any>,regions:any[],onSelect:(id:string)=>void}){
 const ref=useRef<HTMLDivElement>(null);
 const current=useRef(conditions); current.current=conditions; const sceneRef=useRef<THREE.Scene|null>(null); const overlays=useRef<THREE.Group|null>(null);
 useEffect(()=>{
  const host=ref.current!; delete host.dataset.modelLoaded; const scene=new THREE.Scene(); sceneRef.current=scene; const layer=new THREE.Group(); scene.add(layer); overlays.current=layer;scene.background=new THREE.Color('#101b29');
  const camera=new THREE.PerspectiveCamera(42,host.clientWidth/host.clientHeight,.01,300);camera.up.set(0,0,1);camera.position.set(8,7,11);
  const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setSize(host.clientWidth,host.clientHeight);host.appendChild(renderer.domElement);renderer.domElement.dataset.testid='plant-canvas';
  const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,0,2);controls.enableDamping=true;
  scene.add(new THREE.HemisphereLight(0xe8f7ff,0x23344b,3));const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(4,7,10);scene.add(light);
  const grid=new THREE.GridHelper(18,30,0x36506a,0x24364c);grid.rotation.x=Math.PI/2;scene.add(grid);
  let model:THREE.Group|null=null;let cancelled=false;
  fetch('/api/v1/model',{headers:{Authorization:`Bearer ${token}`}}).then(r=>r.arrayBuffer()).then(data=>new GLTFLoader().parse(data,'',g=>{
   if(cancelled)return;model=g.scene;scene.add(model);model.traverse(o=>{if(o instanceof THREE.Mesh){let asset=o.name;while(asset && !current.current[asset] && asset.includes('_'))asset=asset.slice(0,asset.lastIndexOf('_'));o.userData.asset=asset;const status=severity(current.current[asset]);o.material=new THREE.MeshStandardMaterial({color:colors[status],metalness:.32,roughness:.52,transparent:true,opacity:.8});}});
   const box=new THREE.Box3().setFromObject(model);const center=box.getCenter(new THREE.Vector3());controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(8,-10,7));controls.update();host.dataset.modelLoaded='true';
  },e=>{host.dataset.error=String(e)})).catch(e=>{host.dataset.error=String(e)});

  const ray=new THREE.Raycaster();const pointer=new THREE.Vector2();const select=(e:MouseEvent)=>{const bounds=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-bounds.left)/bounds.width*2-1,-(e.clientY-bounds.top)/bounds.height*2+1);ray.setFromCamera(pointer,camera);const hit=ray.intersectObjects(scene.children,true).find(h=>h.object.userData.asset);if(hit)onSelect(hit.object.userData.asset)};
  renderer.domElement.addEventListener('click',select);
  const resize=()=>{camera.aspect=host.clientWidth/host.clientHeight;camera.updateProjectionMatrix();renderer.setSize(host.clientWidth,host.clientHeight)};const ro=new ResizeObserver(resize);ro.observe(host);
  let frame=0;const draw=()=>{frame=requestAnimationFrame(draw);controls.update();renderer.render(scene,camera)};draw();
  return()=>{cancelled=true;cancelAnimationFrame(frame);ro.disconnect();controls.dispose();renderer.dispose();renderer.domElement.removeEventListener('click',select);host.removeChild(renderer.domElement);scene.traverse(o=>{if(o instanceof THREE.Mesh){o.geometry.dispose();(o.material as THREE.Material).dispose()}})}
 },[token,onSelect]);
 useEffect(()=>{sceneRef.current?.traverse(o=>{if(o instanceof THREE.Mesh && o.userData.asset)(o.material as THREE.MeshStandardMaterial).color.set(colors[severity(conditions[o.userData.asset])]);});},[conditions]);
 useEffect(()=>{const layer=overlays.current;if(!layer)return;layer.clear();for(const r of regions){if(!r.bounds_world_m)continue;const b=r.bounds_world_m;layer.add(new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(...b[0]),new THREE.Vector3(...b[1])),0xf3bb64));}},[regions]);
 return <div className="plant" ref={ref} aria-label="Interactive accepted baseline plant"/>;
}
