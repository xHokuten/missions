(()=>{
  const scenes=[...document.querySelectorAll('.landing-scene')];
  const location=document.querySelector('#landing-location');
  const pencilPass=document.querySelector('.landing-pencil-pass');
  const audio=document.querySelector('#landing-audio');
  const toggle=document.querySelector('#soundtrack-toggle');
  const volume=document.querySelector('#soundtrack-volume');
  if(!scenes.length)return;

  let current=0;
  let syncFrame=0;
  let preloadStarted=false;
  const hydrateScene=scene=>{
    if(!scene.dataset.sceneUrl)return;
    scene.style.setProperty('--scene',`url("${scene.dataset.sceneUrl}")`);
    delete scene.dataset.sceneUrl;
  };
  const preloadScenes=()=>{
    if(preloadStarted)return;
    preloadStarted=true;
    const pending=scenes.slice(1);
    const loadNext=()=>{
      const scene=pending.shift();
      if(!scene)return;
      const source=scene.dataset.sceneUrl;
      if(!source){loadNext();return;}
      const image=new Image();
      image.onload=()=>{hydrateScene(scene);loadNext();};
      image.onerror=loadNext;
      image.src=source;
    };
    loadNext();
  };
  const showScene=index=>{
    if(index===current)return;
    const previous=scenes[current];
    previous.classList.remove('active','initial');
    previous.classList.add('leaving');
    current=index;
    const next=scenes[current];
    hydrateScene(next);
    next.classList.remove('leaving');
    next.classList.add('active');
    location.textContent=next.dataset.name;
    pencilPass.classList.remove('draw');
    void pencilPass.offsetWidth;
    pencilPass.classList.add('draw');
    setTimeout(()=>previous.classList.remove('leaving'),900);
  };

  const syncScenesToSong=()=>{
    if(!audio||audio.paused)return;
    if(Number.isFinite(audio.duration)&&audio.duration>0){
      const secondsPerScene=audio.duration/scenes.length;
      const sceneIndex=Math.min(scenes.length-1,Math.floor(audio.currentTime/secondsPerScene));
      showScene(sceneIndex);
    }
    syncFrame=requestAnimationFrame(syncScenesToSong);
  };

  if(audio&&toggle&&volume){
    audio.volume=Number(volume.value);
    volume.addEventListener('input',()=>{audio.volume=Number(volume.value)});
    audio.addEventListener('seeked',()=>{
      if(Number.isFinite(audio.duration)&&audio.duration>0){
        showScene(Math.min(scenes.length-1,Math.floor(audio.currentTime/(audio.duration/scenes.length))));
      }
    });
    toggle.addEventListener('click',async()=>{
      if(audio.paused){
        try{
          preloadScenes();
          await audio.play();
          toggle.textContent='❚❚';
          toggle.setAttribute('aria-label','Pause We Depart For Distant Shores');
          cancelAnimationFrame(syncFrame);
          syncScenesToSong();
        }catch(_error){return}
      }else{
        audio.pause();
        cancelAnimationFrame(syncFrame);
        toggle.textContent='▶';
        toggle.setAttribute('aria-label','Play We Depart For Distant Shores');
      }
    });
  }

  addEventListener('pagehide',()=>cancelAnimationFrame(syncFrame));
})();
