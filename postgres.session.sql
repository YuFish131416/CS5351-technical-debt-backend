ALTER TABLE projects ADD COLUMN IF NOT EXISTS status varchar(50) DEFAULT 'idle';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS current_analysis_id varchar(100);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_analysis_id varchar(100);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_analysis_at timestamptz;
-- 添加 unique 约束（脚本会检查是否存在再添加）
ALTER TABLE projects ADD CONSTRAINT uq_projects_local_path UNIQUE (local_path);