export interface Metadata {
    title: string;
    channel: string;
    duration: string | null;
    thumbnail: string | null;
}

export interface ProcessResponse {
    metadata: Metadata;
    download_url: string | null;
}