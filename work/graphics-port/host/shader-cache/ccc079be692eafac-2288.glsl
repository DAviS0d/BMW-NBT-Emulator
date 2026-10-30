uniform mat4 u_MVPMatrix;

attribute vec4 a_Position;
attribute vec2 a_TextureCoordinate;

varying vec2 vTexCoord;

uniform float u_alphaFalloffStart;
uniform float u_alphaFalloffEnd;
varying mediump float vFalloff;

void main()
{
    vec3 position = a_Position.xyz;

    gl_Position = u_MVPMatrix * a_Position;
    vTexCoord = vec2(a_TextureCoordinate.x, 1.-a_TextureCoordinate.y);
    
    float alphaLength = 1./(u_alphaFalloffEnd - u_alphaFalloffStart);
    vFalloff = 1. - (vTexCoord.x - u_alphaFalloffStart) * alphaLength;
}