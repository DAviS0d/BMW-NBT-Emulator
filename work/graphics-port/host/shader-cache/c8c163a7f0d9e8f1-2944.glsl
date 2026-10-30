precision highp float;

struct material
{
    vec4  ambient;
    vec4  diffuse;
    vec4  emissive;
    vec4  specular;
    float shininess;
};

attribute vec4 a_Position;
attribute vec2 a_TextureCoordinate;

varying vec2 vTexCoord;
varying vec4 vColor;
varying vec2 vLineEquation;
varying float vLinePos;

uniform material u_Material;
uniform float    u_PointSize;
uniform mat4     u_transformMatrix;
uniform vec4     u_position2DImage;
uniform vec4     u_texcoord2DImage;

void main(void)
{
  vec2 pos = a_Position.xy * u_position2DImage.zw + u_position2DImage.xy;
  vLinePos = a_Position.z;
  vLineEquation = a_TextureCoordinate;
  
  vTexCoord = a_TextureCoordinate * u_texcoord2DImage.zw + u_texcoord2DImage.xy;
  vColor = u_Material.diffuse;
  
  vec4 transPos = u_transformMatrix * vec4(pos, 0., 1.);
  transPos /= transPos.w;
  gl_Position = vec4(transPos.xy, 0., 1.);
}
