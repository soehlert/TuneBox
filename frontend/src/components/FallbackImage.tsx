import { useState } from 'react';

interface FallbackImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  src: string;
  alt: string;
  type?: 'artist' | 'album' | 'track';
  fetchPriority?: 'high' | 'low' | 'auto';
  loading?: 'eager' | 'lazy';
}

export const FallbackImage = ({
  src,
  alt,
  type = 'album',
  className = '',
  style,
  loading = 'lazy',
  fetchPriority = 'auto',
  ...props
}: FallbackImageProps) => {
  const [error, setError] = useState(false);

  if (error || !src) {
    const iconName = type === 'artist' ? 'person' : 'album';
    return (
      <div
        className={`${className} fallback-image-placeholder`}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(255, 255, 255, 0.05)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          color: 'rgba(255, 255, 255, 0.35)',
          userSelect: 'none',
          boxSizing: 'border-box',
          ...style,
        }}
        title={alt}
      >
        <span className="material-symbols-outlined" style={{ fontSize: '28px' }}>
          {iconName}
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      loading={loading}
      fetchPriority={fetchPriority}
      decoding="async"
      className={className}
      style={style}
      onError={() => setError(true)}
      {...props}
    />
  );
};
