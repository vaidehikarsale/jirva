export default function ComingSoonPage({ icon: Icon, title, description }) {
  return (
    <div className="panel coming-soon">
      <div className="coming-soon-icon"><Icon width={28} height={28} /></div>
      <h1>{title}</h1>
      <p>{description}</p>
      <span className="badge badge-neutral">Coming soon</span>
    </div>
  );
}
