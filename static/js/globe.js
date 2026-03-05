/**
 * SHIELD — 3D Interactive Threat Globe
 * Built with Three.js — shows scam intensity across Indian cities
 */

let globeScene, globeCamera, globeRenderer, globeObj, globeInitialized = false;
let isDragging = false, prevMouse = { x: 0, y: 0 };
let targetRotY = 0.5, targetRotX = 0.3;
let currentRotY = 0.5, currentRotX = 0.3;
const cityMeshes = [];

const CITIES = [
    { name: 'Delhi NCR', lat: 28.6139, lon: 77.2090, count: 42, topScam: 'Fake KYC', pct: '54%', trend: '+18%' },
    { name: 'Mumbai', lat: 19.0760, lon: 72.8777, count: 38, topScam: 'Digital Arrest', pct: '41%', trend: '+12%' },
    { name: 'Jaipur', lat: 26.9124, lon: 75.7873, count: 31, topScam: 'UPI Fraud', pct: '37%', trend: '+9%' },
    { name: 'Pune', lat: 18.5204, lon: 73.8567, count: 27, topScam: 'Lottery Scam', pct: '29%', trend: '-5%' },
    { name: 'Bangalore', lat: 12.9716, lon: 77.5946, count: 19, topScam: 'Investment Fraud', pct: '33%', trend: '+22%' },
    { name: 'Chennai', lat: 13.0827, lon: 80.2707, count: 14, topScam: 'Utility Threats', pct: '28%', trend: '+6%' },
    { name: 'Kolkata', lat: 22.5726, lon: 88.3639, count: 11, topScam: 'Digital Arrest', pct: '45%', trend: '-2%' },
    { name: 'Lucknow', lat: 26.8467, lon: 80.9462, count: 7, topScam: 'Fake KYC', pct: '40%', trend: '+3%' },
    { name: 'Hyderabad', lat: 17.3850, lon: 78.4867, count: 16, topScam: 'UPI Fraud', pct: '31%', trend: '+15%' },
    { name: 'Ahmedabad', lat: 23.0225, lon: 72.5714, count: 9, topScam: 'Lottery Scam', pct: '35%', trend: '+7%' },
];

function latLonToVec3(lat, lon, radius) {
    const phi = (90 - lat) * (Math.PI / 180);
    const theta = (lon + 180) * (Math.PI / 180);
    return new THREE.Vector3(
        -radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta)
    );
}

function getIntensityColor(count) {
    if (count >= 30) return new THREE.Color(1.0, 0.2, 0.2);   // Red
    if (count >= 15) return new THREE.Color(1.0, 0.53, 0.2);  // Orange
    return new THREE.Color(1.0, 0.8, 0.2);                     // Yellow
}

function initGlobe() {
    if (globeInitialized) return;
    const container = document.getElementById('globe-container');
    if (!container) return;

    const w = container.clientWidth;
    const h = Math.max(container.clientHeight, 500);

    // Scene
    globeScene = new THREE.Scene();

    // Camera
    globeCamera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
    globeCamera.position.z = 3.2;

    // Renderer
    globeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    globeRenderer.setSize(w, h);
    globeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    globeRenderer.setClearColor(0x000000, 0);
    container.appendChild(globeRenderer.domElement);

    // Globe group
    globeObj = new THREE.Group();

    // Wireframe sphere (earth)
    const sphereGeo = new THREE.SphereGeometry(1, 48, 48);
    const wireframe = new THREE.WireframeGeometry(sphereGeo);
    const wireMat = new THREE.LineBasicMaterial({ color: 0x4338ca, opacity: 0.15, transparent: true });
    const wireLines = new THREE.LineSegments(wireframe, wireMat);
    globeObj.add(wireLines);

    // Solid dark sphere underneath
    const solidMat = new THREE.MeshBasicMaterial({ color: 0x0c0a1a, opacity: 0.85, transparent: true });
    const solidSphere = new THREE.Mesh(sphereGeo, solidMat);
    solidSphere.scale.setScalar(0.995);
    globeObj.add(solidSphere);

    // Atmosphere glow
    const glowGeo = new THREE.SphereGeometry(1.08, 48, 48);
    const glowMat = new THREE.MeshBasicMaterial({
        color: 0x6366f1, opacity: 0.06, transparent: true, side: THREE.BackSide
    });
    globeObj.add(new THREE.Mesh(glowGeo, glowMat));

    // Latitude/longitude grid lines
    const gridMat = new THREE.LineBasicMaterial({ color: 0x6366f1, opacity: 0.08, transparent: true });
    for (let lat = -60; lat <= 60; lat += 30) {
        const points = [];
        for (let lon = 0; lon <= 360; lon += 5) {
            points.push(latLonToVec3(lat, lon, 1.002));
        }
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        globeObj.add(new THREE.Line(lineGeo, gridMat));
    }
    for (let lon = 0; lon < 360; lon += 30) {
        const points = [];
        for (let lat = -90; lat <= 90; lat += 5) {
            points.push(latLonToVec3(lat, lon, 1.002));
        }
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        globeObj.add(new THREE.Line(lineGeo, gridMat));
    }

    // === CONTINENT / COUNTRY OUTLINES ===
    const continentMat = new THREE.LineBasicMaterial({ color: 0x8b8fc7, opacity: 0.35, transparent: true });
    const indiaMat = new THREE.LineBasicMaterial({ color: 0x22d3ee, opacity: 0.7, transparent: true, linewidth: 2 });

    function drawOutline(coords, material) {
        const pts = coords.map(c => latLonToVec3(c[0], c[1], 1.005));
        const geo = new THREE.BufferGeometry().setFromPoints(pts);
        globeObj.add(new THREE.Line(geo, material));
    }

    // India (highlighted)
    drawOutline([
        [8.07, 77.55], [8.3, 73.5], [10.5, 76], [12, 75], [14, 74.8], [16, 73.3], [17.5, 73], [19.1, 72.8],
        [20.7, 73], [21, 72.6], [22.5, 69], [23.5, 68.5], [24.5, 68.8], [25, 70.5], [26, 70.2], [27, 70],
        [28.5, 70.5], [29.5, 71.5], [30.5, 72], [31, 74.5], [32, 74.8], [33, 75.5], [34, 74], [35, 75], [36.5, 75],
        [37, 76.5], [35, 77.8], [34, 78.5], [32.5, 79], [31, 80.5], [30, 81], [29, 84], [27.5, 85], [27, 88],
        [26.5, 88.5], [25, 89], [24, 89.5], [22, 90.5], [22, 92], [21, 92.5], [22.5, 93.5], [24.5, 94.5], [26, 95], [27, 97],
        [28, 97.5], [27, 96], [26, 93], [25, 93], [22.5, 93.5], [21.5, 92.5], [22, 90], [21.5, 88.5], [21.8, 87.5],
        [21, 86.5], [20, 86.8], [19, 85], [18, 83.5], [17, 82.5], [16, 81.5], [15, 80], [13.5, 80.5], [12, 80],
        [11, 79.8], [9, 79], [8.5, 78], [8.07, 77.55]
    ], indiaMat);

    // Sri Lanka
    drawOutline([[10, 80], [9.5, 80.3], [7.5, 81.5], [6, 80.5], [6.5, 79.7], [8, 79.8], [9.5, 80], [10, 80]], continentMat);

    // Southeast Asia (simplified)
    drawOutline([[10, 98], [15, 100], [18, 105], [21, 106], [22, 108], [18, 110], [12, 109], [8, 105], [5, 103], [1, 104], [-2, 106], [-6, 105], [-8, 110]], continentMat);

    // Middle East
    drawOutline([[30, 48], [32, 45], [33, 44], [37, 43], [38, 48], [36, 53], [32, 52], [30, 50], [26, 56], [24, 56], [22, 55], [18, 52], [13, 45], [12, 43], [14, 42], [18, 40], [20, 40], [25, 37], [28, 35], [30, 35], [32, 36], [35, 36], [37, 40], [30, 48]], continentMat);

    // Africa (simplified)
    drawOutline([[37, 10], [35, 0], [32, -5], [30, -10], [25, -15], [20, -17], [15, -17], [10, -15], [5, -10], [5, -1], [0, 9], [-5, 12], [-10, 14], [-15, 12], [-20, 15], [-25, 17], [-30, 18], [-34, 18], [-34, 26], [-33, 28], [-28, 32], [-25, 35], [-20, 36], [-15, 40], [-5, 40], [5, 42], [10, 45], [15, 32], [20, 40], [25, 35], [28, 35], [30, 32], [32, 32], [37, 10]], continentMat);

    // Europe (simplified)
    drawOutline([[36, -6], [37, 0], [40, 0], [43, -8], [44, -1], [46, 1], [47, 5], [49, 2], [51, 3], [52, 5], [54, 8], [56, 10], [58, 11], [60, 5], [62, 5], [64, 14], [66, 14], [68, 16], [70, 20], [71, 26], [70, 28], [65, 30], [60, 30], [55, 28], [50, 30], [46, 37], [43, 40], [42, 44], [40, 44], [38, 40], [37, 25], [37, 15], [36, 12], [38, 10], [37, 0], [36, -6]], continentMat);

    // East Asia
    drawOutline([[22, 108], [25, 108], [28, 105], [30, 103], [33, 105], [35, 105], [36, 103], [38, 106], [39, 110], [37, 117], [35, 119], [32, 120], [30, 122], [28, 121], [25, 120], [24, 118], [22, 114], [22, 108]], continentMat);

    // Japan
    drawOutline([[31, 131], [33, 130], [35, 132], [36, 136], [37, 137], [39, 140], [41, 140], [43, 141], [45, 142], [44, 145], [42, 143], [40, 139], [38, 137], [36, 136], [34, 132], [31, 131]], continentMat);

    // North America (simplified)
    drawOutline([[10, -84], [15, -88], [20, -97], [25, -97], [28, -96], [30, -90], [32, -85], [30, -82], [25, -80], [20, -75], [30, -80], [35, -76], [40, -74], [42, -70], [43, -66], [45, -62], [47, -60], [50, -55], [52, -56], [55, -60], [60, -65], [64, -62], [66, -60], [68, -55], [70, -60], [72, -68], [72, -80], [70, -90], [68, -100], [66, -110], [64, -120], [60, -140], [58, -152], [55, -160], [60, -165], [62, -155], [63, -145], [64, -140], [60, -130], [55, -125], [48, -123], [45, -124], [40, -124], [38, -122], [35, -118], [33, -117], [32, -115], [30, -114], [25, -110], [20, -105], [18, -103], [16, -97], [12, -85], [10, -84]], continentMat);

    // South America (simplified)
    drawOutline([[10, -62], [10, -68], [5, -76], [0, -80], [-5, -81], [-10, -77], [-15, -75], [-20, -70], [-25, -65], [-30, -57], [-35, -57], [-38, -57], [-42, -63], [-46, -67], [-50, -68], [-53, -70], [-55, -70], [-55, -65], [-52, -60], [-48, -55], [-42, -50], [-38, -48], [-35, -52], [-30, -48], [-25, -44], [-20, -40], [-15, -35], [-10, -35], [-3, -50], [5, -60], [10, -62]], continentMat);

    // Australia
    drawOutline([[-12, 130], [-14, 127], [-17, 123], [-20, 119], [-22, 114], [-25, 114], [-28, 114], [-31, 116], [-33, 118], [-35, 119], [-36, 137], [-38, 141], [-38, 145], [-37, 148], [-35, 151], [-33, 152], [-30, 153], [-27, 153], [-24, 152], [-20, 149], [-16, 146], [-13, 143], [-12, 136], [-12, 130]], continentMat);

    // City markers
    CITIES.forEach(city => {
        const pos = latLonToVec3(city.lat, city.lon, 1.01);
        const color = getIntensityColor(city.count);
        const intensity = city.count / 42; // normalize to max

        // Pin dot
        const dotGeo = new THREE.SphereGeometry(0.015 + intensity * 0.015, 16, 16);
        const dotMat = new THREE.MeshBasicMaterial({ color: color });
        const dot = new THREE.Mesh(dotGeo, dotMat);
        dot.position.copy(pos);
        dot.userData = city;
        globeObj.add(dot);
        cityMeshes.push(dot);

        // Pulsing ring
        const ringGeo = new THREE.RingGeometry(0.03 + intensity * 0.04, 0.035 + intensity * 0.05, 32);
        const ringMat = new THREE.MeshBasicMaterial({
            color: color, opacity: 0.5, transparent: true, side: THREE.DoubleSide
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.position.copy(pos);
        ring.lookAt(new THREE.Vector3(0, 0, 0));
        ring.userData = { _pulse: true, _baseScale: 1, _city: city.name };
        globeObj.add(ring);

        // Vertical spike
        const spikeHeight = 0.05 + intensity * 0.15;
        const spikeGeo = new THREE.CylinderGeometry(0.003, 0.003, spikeHeight, 8);
        const spikeMat = new THREE.MeshBasicMaterial({ color: color, opacity: 0.6, transparent: true });
        const spike = new THREE.Mesh(spikeGeo, spikeMat);
        const dir = pos.clone().normalize();
        spike.position.copy(pos.clone().add(dir.clone().multiplyScalar(spikeHeight / 2)));
        spike.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        globeObj.add(spike);
    });

    // Connection arcs between nearby cities
    const arcMat = new THREE.LineBasicMaterial({ color: 0x6366f1, opacity: 0.12, transparent: true });
    for (let i = 0; i < CITIES.length; i++) {
        for (let j = i + 1; j < CITIES.length; j++) {
            const p1 = latLonToVec3(CITIES[i].lat, CITIES[i].lon, 1.01);
            const p2 = latLonToVec3(CITIES[j].lat, CITIES[j].lon, 1.01);
            const dist = p1.distanceTo(p2);
            if (dist < 1.2) {
                const mid = p1.clone().add(p2).multiplyScalar(0.5);
                mid.normalize().multiplyScalar(1.01 + dist * 0.15);
                const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
                const pts = curve.getPoints(20);
                const arcGeo = new THREE.BufferGeometry().setFromPoints(pts);
                globeObj.add(new THREE.Line(arcGeo, arcMat));
            }
        }
    }

    // Rotate to show India
    globeObj.rotation.y = -1.35;
    globeObj.rotation.x = 0.3;
    targetRotY = -1.35;
    targetRotX = 0.3;
    currentRotY = -1.35;
    currentRotX = 0.3;

    globeScene.add(globeObj);

    // Mouse interaction
    const el = globeRenderer.domElement;
    el.addEventListener('mousedown', onGlobeMouseDown);
    el.addEventListener('mousemove', onGlobeMouseMove);
    el.addEventListener('mouseup', onGlobeMouseUp);
    el.addEventListener('mouseleave', onGlobeMouseUp);
    el.addEventListener('touchstart', onGlobeTouchStart, { passive: false });
    el.addEventListener('touchmove', onGlobeTouchMove, { passive: false });
    el.addEventListener('touchend', onGlobeMouseUp);

    // Resize
    window.addEventListener('resize', () => {
        const nw = container.clientWidth;
        const nh = Math.max(container.clientHeight, 500);
        globeCamera.aspect = nw / nh;
        globeCamera.updateProjectionMatrix();
        globeRenderer.setSize(nw, nh);
    });

    // Raycaster for hover
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    el.addEventListener('mousemove', (e) => {
        const rect = el.getBoundingClientRect();
        mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(mouse, globeCamera);
        const hits = raycaster.intersectObjects(cityMeshes);
        const tooltip = document.getElementById('globe-tooltip');
        if (hits.length > 0) {
            const city = hits[0].object.userData;
            document.getElementById('gt-city').textContent = city.name;
            document.getElementById('gt-count').textContent = city.count + ' scams detected';
            document.getElementById('gt-type').textContent = 'Top: ' + city.topScam + ' (' + city.pct + ')';
            document.getElementById('gt-trend').textContent = city.trend + ' this week';
            tooltip.style.display = 'block';
            tooltip.style.left = (e.clientX - container.getBoundingClientRect().left + 15) + 'px';
            tooltip.style.top = (e.clientY - container.getBoundingClientRect().top - 20) + 'px';
        } else {
            tooltip.style.display = 'none';
        }
    });

    globeInitialized = true;
    animateGlobe();
}

function onGlobeMouseDown(e) {
    isDragging = true;
    prevMouse = { x: e.clientX, y: e.clientY };
}

function onGlobeMouseMove(e) {
    if (!isDragging) return;
    const dx = e.clientX - prevMouse.x;
    const dy = e.clientY - prevMouse.y;
    targetRotY += dx * 0.005;
    targetRotX += dy * 0.005;
    targetRotX = Math.max(-1.2, Math.min(1.2, targetRotX));
    prevMouse = { x: e.clientX, y: e.clientY };
}

function onGlobeMouseUp() { isDragging = false; }

function onGlobeTouchStart(e) {
    e.preventDefault();
    if (e.touches.length === 1) {
        isDragging = true;
        prevMouse = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
}

function onGlobeTouchMove(e) {
    e.preventDefault();
    if (!isDragging || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - prevMouse.x;
    const dy = e.touches[0].clientY - prevMouse.y;
    targetRotY += dx * 0.005;
    targetRotX += dy * 0.005;
    targetRotX = Math.max(-1.2, Math.min(1.2, targetRotX));
    prevMouse = { x: e.touches[0].clientX, y: e.touches[0].clientY };
}

function animateGlobe() {
    requestAnimationFrame(animateGlobe);
    if (!globeObj) return;

    // Smooth rotation
    currentRotY += (targetRotY - currentRotY) * 0.08;
    currentRotX += (targetRotX - currentRotX) * 0.08;
    globeObj.rotation.y = currentRotY;
    globeObj.rotation.x = currentRotX;

    // Auto-rotate slowly when not dragging
    if (!isDragging) {
        targetRotY += 0.001;
    }

    // Pulse rings
    const time = Date.now() * 0.002;
    globeObj.children.forEach(child => {
        if (child.userData && child.userData._pulse) {
            const scale = 1 + Math.sin(time + child.position.x * 5) * 0.3;
            child.scale.setScalar(scale);
            child.material.opacity = 0.3 + Math.sin(time + child.position.y * 3) * 0.2;
        }
    });

    globeRenderer.render(globeScene, globeCamera);
}
