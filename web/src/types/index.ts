export interface ProjectSummary {
  name: string;
  platform: string | null;
  game_title: string | null;
}

export interface RomMetadata {
  game_title: string;
  game_code: string;
  maker_code: string;
  maker_name: string;
  software_version: number;
  region: string;
  rom_size_bytes: number;
  rom_size_mb: number;
  checksum_valid: boolean;
}

export interface KnowledgeFile {
  path: string;
  name: string;
  category: string;
  size: number;
}

export interface ProjectDetail {
  name: string;
  platform: string;
  game_title: string | null;
  created_at: string | null;
  rom: RomMetadata | null;
  stats: {
    discoveries: number;
    golden: number;
    graph_nodes: number;
    graph_edges: number;
  };
  knowledge: KnowledgeFile[];
}

export interface InitProjectResult {
  name: string;
  classification: {
    source: string;
    destination: string;
    reason: string;
  }[];
  notes: string | null;
}
