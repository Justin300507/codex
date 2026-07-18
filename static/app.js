const {useEffect, useState} = React;
const money = (v) => v === 0 ? "Free" : "Rs " + v;

function App() {
  const [stations, setStations] = useState([]);
  const [form, setForm] = useState({
    name: "",
    destination: "",
    origin_station: "Vyttila",
    budget_range: "no_limit",
    max_walk_m: 300,
    preference: "any",
    meetup_tag: "",
  });
  const [confirm, setConfirm] = useState(null);
  const [recommendation, setRecommendation] = useState(null);
  const [poolOffer, setPoolOffer] = useState(null);
  const [groups, setGroups] = useState([]);
  const [stats, setStats] = useState({});
  const [weather, setWeather] = useState({});
  const [stands, setStands] = useState([]);
  const [autoStand, setAutoStand] = useState(null);
  const [cabStand, setCabStand] = useState(null);
  const [geo, setGeo] = useState("Locating near you...");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const api = async (path, opts) => {
    const r = await fetch(path, opts);
    const data = await r.json();
    if (!r.ok) throw new Error(Array.isArray(data.detail) ? data.detail[0].msg : data.detail || "Request failed");
    return data;
  };

  async function load() {
    try {
      const [g, s, w] = await Promise.all([api("/groups"), api("/stats"), api("/weather")]);
      setGroups(g.groups);
      setStats(s);
      setWeather(w);
    } catch (e) {}
  }

  useEffect(() => {
    api("/stations").then(setStations);
    load();
    const t = setInterval(load, 3000);
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        () => setGeo("Confirmed near Vyttila Metro"),
        () => setGeo("Location is display-only")
      );
    }
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    api("/bus-stands?station=" + encodeURIComponent(form.origin_station))
      .then((b) => {
        setStands(b.stands || []);
        setAutoStand(b.auto_stand || null);
        setCabStand(b.cab_stand || null);
      })
      .catch(() => {
        setStands([]);
        setAutoStand(null);
        setCabStand(null);
      });
  }, [form.origin_station]);

  const change = (e) => setForm({
    ...form,
    [e.target.name]: e.target.name === "max_walk_m" ? +e.target.value : e.target.value,
  });

  async function locate(e) {
    e.preventDefault();
    if (!form.destination.trim()) return;
    setError("");
    setLoading(true);
    try {
      const m = await api("/locate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({destination: form.destination}),
      });
      setConfirm(m);
    } catch (err) {
      setError(err.message || "Could not find that destination. Please try a nearby landmark.");
    } finally {
      setLoading(false);
    }
  }

  async function submit() {
    setError("");
    setLoading(true);
    try {
      const r = await api("/passengers", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({...form, lat: confirm.lat, lng: confirm.lng}),
      });
      setRecommendation({...r.recommendation, distance: r.passenger.distance_km, pool: r.pooling_available});
      setPoolOffer(r.pooling_available ? {...(r.pool_offer || {waiting: true}), passengerId: r.passenger.id} : null);
      setWeather(r.weather || {});
      setConfirm(null);
      setForm({...form, name: "", destination: "", meetup_tag: ""});
      load();
    } catch (err) {
      setError(err.message || "Could not save this trip. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function joinPool() {
    const r = await api(`/passengers/${poolOffer.passengerId}/join-pool`, {method: "POST"});
    setGroups(r.groups);
    setPoolOffer({...poolOffer, joined: true});
  }

  function share() {
    const text = `LastMile Kochi Metro: heading to ${recommendation?.distance || ""} km destination. Meet at Vyttila Metro main exit.`;
    navigator.share ? navigator.share({title: "Share my ride", text}) : window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank");
  }

  return <main className="shell">
    <header className="hero">
      <div className="brand"><div className="mark">LM</div><div><div className="eyebrow">KOCHI METRO - LAST-MILE COMPANION</div><h1>LastMile</h1><div className="location">{geo}</div></div></div>
      <div className="status">Demo network live</div>
    </header>

    <section className="grid">
      <form className="card" onSubmit={locate}>
        <h2>Plan your onward trip</h2>
        <p className="sub">Find a practical ride from the metro with safe, opt-in pooling.</p>
        <div className="station"><span>MT</span><div><b>Metro origin</b><br/><small>All 25 Kochi Metro stations supported</small></div></div>
        <div className="fields">
          <label>Name<input required name="name" value={form.name} onChange={change} placeholder="Your name"/></label>
          <label>Origin station<select name="origin_station" value={form.origin_station} onChange={change}>{stations.map((s) => <option key={s.name}>{s.name}</option>)}</select></label>
          <label className="full">Destination<input required maxLength="1200" name="destination" value={form.destination} onChange={change} placeholder="e.g. Thripunithura Hill Palace, or your street"/></label>
          <label>Budget<select name="budget_range" value={form.budget_range} onChange={change}><option value="under_100">Under Rs 100</option><option value="100_250">Rs 100-250</option><option value="250_500">Rs 250-500</option><option value="no_limit">No limit</option></select></label>
          <label>Travel preference<select name="preference" value={form.preference} onChange={change}><option value="any">Any ride</option><option value="women-only">Women-only</option><option value="quiet">Quiet ride</option></select>{form.preference === "women-only" && <span className="hint">Self-declared preference. Please use responsibly to support safer ride matching.</span>}</label>
          <label>Max walk: {form.max_walk_m}m<input className="range" type="range" min="0" max="1000" step="50" name="max_walk_m" value={form.max_walk_m} onChange={change}/></label>
          <label>Meetup tag<input name="meetup_tag" value={form.meetup_tag} onChange={change} placeholder="e.g. Blue backpack"/></label>
        </div>
        {error && <p className="error">{error}</p>}
        <div className="actions"><button className="primary" disabled={loading}>{loading ? "Finding location..." : "Find my last mile"}</button></div>
      </form>

      <aside className="card">
        <h2>Metro-to-terminal connection</h2>
        <p className="sub">Nearest bus, auto, and cab pickup after alighting at {form.origin_station}.</p>
        {weather.available && <div className="weather">{weather.temperature} C - {weather.condition}{weather.rain && " - auto/cab prioritized over walking"}</div>}
        <div className="station"><span>W</span><div><b>Walk-to-transfer guidance</b><br/><small>Distances are estimated from the selected Metro station.</small></div></div>
        {stands.map((stand) => <div className="bus-board" key={stand.name}>
          <b>Bus: {stand.name} - {stand.walk_m}m walk</b>
          <small>{stand.routes.join(" - ")}</small>
          <small>{stand.frequency}</small>
        </div>)}
        {autoStand && <div className="auto-board"><b>Auto: {autoStand.name} - {autoStand.walk_m}m walk</b><small>Direct last-mile rides are available from this pickup point.</small></div>}
        {cabStand && <div className="auto-board"><b>Cab: {cabStand.name} - {cabStand.walk_m}m walk</b><small>Use app cab pickup or local taxi queue where available.</small></div>}
        <div className="station"><span>S</span><div><b>Safety-first sharing</b><br/><small>Pooling is always opt-in. No tracking or contacts are stored.</small></div></div>
        {recommendation && <Recommendation data={recommendation} onShare={share}/>}
        {poolOffer && <PoolOffer offer={poolOffer} onJoin={joinPool}/>}
      </aside>
    </section>

    <section>
      <div className="dashhead"><div><div className="eyebrow">LIVE COMMUNITY DASHBOARD</div><h2>Ride pools leaving from Vyttila</h2></div><small className="sub">Refreshes every 3 seconds</small></div>
      <div className="stats"><Stat label="Passengers" value={stats.total_passengers || "-"}/><Stat label="Groups formed" value={stats.groups_formed || "-"}/><Stat label="Est. saved" value={"Rs " + (stats.money_saved || 0)}/><Stat label="CO2 avoided" value={(stats.co2_saved || 0) + " kg"}/></div>
      <p className="sub">Most requested area: <b>{stats.most_requested || "-"}</b></p>
      <div className="groups">{groups.map((g) => <Group key={g.group_id} g={g}/>)}</div>
    </section>

    {confirm && <div className="modal"><div className="card"><div className="eyebrow">CONFIRM YOUR DESTINATION</div><h2>{confirm.source === "google" ? "Did you mean:" : "Closest match:"}</h2><p className="sub"><b>{confirm.address}</b><br/>{confirm.source === "google" ? "Google geocoding match" : "Fallback landmark match - is this close enough?"}</p><div className="actions"><button className="secondary" onClick={() => setConfirm(null)}>No, edit it</button><button className="primary" onClick={submit} disabled={loading}>Yes, continue</button></div></div></div>}
  </main>;
}

function Recommendation({data, onShare}) {
  const options = data.options || [
    {mode: "bus", label: "Bus", fare: data.fares.bus},
    {mode: "auto", label: "Auto", fare: data.fares.auto},
    {mode: "cab", label: "Cab", fare: data.fares.cab},
  ];
  return <div className="recommend">
    <span className="pill">{data.distance} km away</span><span className="pill">{data.time} min est.</span>
    <h3>Recommended: {data.mode} - {money(data.fare)}</h3>
    <p className="sub">{data.reasoning}</p>
    <div className="compare">{options.map((o) => <div key={o.mode}>{o.label}<b>{money(o.fare)}</b>{o.time && <small>{o.time} min est.</small>}</div>)}</div>
    {data.pool && <button className="secondary" style={{marginTop: 12}} onClick={onShare}>Share my ride</button>}
    <p className="notice">Bus timing is not live. Fares are estimates from the demo pricing model.</p>
  </div>;
}

function PoolOffer({offer, onJoin}) {
  const hasMatch = !offer.waiting;
  return <div className="pool-offer">
    <div className="eyebrow">OPTIONAL POOL MATCH</div>
    <h3>{offer.joined ? (hasMatch ? "You joined the pool" : "You joined the matching queue") : (hasMatch ? `Pool with ${offer.partner_name}?` : "No match yet - join the pool queue?")}</h3>
    <p className="sub">{offer.joined ? (hasMatch ? `Meet at ${offer.meetup}. Your match will appear on the dashboard.` : "We will keep this rider available for compatible people from the same station.") : hasMatch ? `Share a ${offer.mode} with ${offer.partner_name} (${offer.partner_tag}). ${offer.riders} riders split the fare: ${money(offer.solo_fare)} to ${money(offer.shared_fare)}.` : "No compatible rider is waiting right now. Join the queue only if you want to be considered for a future nearby match."}</p>
    {!offer.joined && <button className="primary" onClick={onJoin}>{hasMatch ? `Join pool - save ${money(offer.saving)}` : "Join matching queue"}</button>}
    <p className="notice">Opt-in only - choosing a solo ride never adds you to a pool.</p>
  </div>;
}

function Stat({label, value}) {
  return <div className="stat"><span>{label}</span><b>{value}</b></div>;
}

function Group({g}) {
  return <article className="group">
    <span className="pill">{g.suggested_mode === "cab" ? "Cab" : "Auto"} - Rs {g.cost_per_member}/person</span>
    {g.women_only && <div className="match">WOMEN-ONLY MATCH</div>}
    <h3>{g.members.map((m) => m.name).join(" + ")}</h3>
    <div>{g.members.map((m) => <span className="tag" key={m.name}>{m.tag || m.name}</span>)}</div>
    <p>{g.ai_reasoning}</p>
    <small>{g.meetup_point_at_station}</small>
  </article>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
