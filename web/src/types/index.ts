export interface ProjectSummary {
  name: string;
  platform: string | null;
  game_title: string | null;
}

export interface ProjectDetail {
  name: string;
  platform: string;
  game_title: string | null;
  created_at: string | null;
  stats: {
    discoveries: number;
    golden: number;
    graph_nodes: number;
    graph_edges: number;
  };
}

export interface KnowledgeFile {
  path: string;
  type: string;
  size: number;
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
