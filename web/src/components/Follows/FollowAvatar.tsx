import React, { useState } from 'react';
import * as api from '../../api';

interface FollowAvatarProps {
  secUid: string;
  nickname?: string | null;
  className?: string;
}

/**
 * 特别关注博主头像：走后端本地化路由（远程 CDN 链接会过期）；
 * 未落盘/下载失败时回退为昵称首字符渐变圆。
 */
export const FollowAvatar: React.FC<FollowAvatarProps> = ({ secUid, nickname, className = '' }) => {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className={`bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white font-bold select-none shrink-0 ${className}`}
      >
        {(nickname || '?').trim().charAt(0).toUpperCase() || '?'}
      </div>
    );
  }
  return (
    <img
      src={api.followAvatarUrl(secUid)}
      alt={nickname || ''}
      onError={() => setFailed(true)}
      className={`object-cover shrink-0 ${className}`}
    />
  );
};
