import { useState } from 'react';

interface FallbackImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  src: string;
  alt: string;
  type?: 'artist' | 'album' | 'track';
}

export const FallbackImage = ({
  src,
  alt,
  type = 'album',
  className = '',
  style,
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
      className={className}
      style={style}
      onError={() => setError(true)}
      {...props}
    />
  );
};
