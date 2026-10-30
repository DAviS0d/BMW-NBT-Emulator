
precision highp float;

uniform mat4  u_transformMatrix;
uniform vec4  u_position2DImage;
uniform vec4  u_texcoord2DImage;

attribute vec4 a_Position;
attribute vec2 a_TextureCoordinate;

varying mediump vec2 vTexCoord;

void main()
{
  vec2 pos = a_Position.xy * u_position2DImage.zw + u_position2DImage.xy;
  vTexCoord = a_TextureCoordinate * u_texcoord2DImage.zw + u_texcoord2DImage.xy;
  
  vec4 transPos = u_transformMatrix * vec4(pos, 0., 1.);
  transPos /= transPos.w;
  gl_Position = vec4(transPos.xy, a_Position.z, 1.);
}
